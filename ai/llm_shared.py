"""Shared LLM classification helpers (prompt, parsing, offline fallback)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from ai.editorial_filter import is_editorial_scope
from ai.tag_rules import refine_tags
from bot.config import EDITORIAL_CRITERIA
from db.models import Categoria
from medios_tiers import tier_label
from reports.tags import validate_tags

SYSTEM_PROMPT_BASE = """Eres un asistente editorial especializado en libros, literatura e industria editorial.

Tu misión: redactar píldoras informativas precisas que den una imagen fiel de lo ocurrido en el mundo editorial en las últimas horas — qué ha pasado, por qué importa y desde qué ángulo lo cuenta cada medio.

Para cada artículo recibirás titular, resumen, fuente, tier del medio, fecha de publicación, categoría prevista e idioma.

Responde SOLO con JSON válido:
{
  "categoria": "ideas" | "noticias",
  "relevance_score": number,
  "en_alcance": boolean,
  "resumen_generado": string,
  "titular_traducido": string,
  "tags": string[]
}

Tags editoriales (obligatorio: 1-3 slugs de esta lista):
- ficcion: Ficción (novelas, relatos, autoficción)
- no_ficcion: No ficción (memorias, biografías, divulgación no ensayística)
- literatura_traducida: Literatura traducida (obras extranjeras publicadas en el mercado local)
- literatura_local: Literatura local (autores del país/mercado del medio)
- ensayo_literario: Ensayo literario/filosófico
- ensayo_politico: Ensayo político/actualidad con eje editorial o cultural
- poesia: Poesía
- lij: Infantil y juvenil (LIJ)
- comic: Cómic y novela gráfica
- mundo_editorial: Mundo editorial (fusiones, adquisiciones, cierres de sellos, cambios de dirección)
- derechos_traducciones: Derechos y traducciones (ventas de derechos, subastas, adelantos)
- ia_tecnologia: IA y tecnología editorial
- librerias_distribucion: Librerías y distribución (aperturas, cierres, retail)
- audiolibros_digital: Audiolibros y digital
- ferias_premios: Ferias y premios (Frankfurt, Guadalajara, Booker, Nobel, Planeta, etc.)

Elige el tag principal y hasta 2 secundarios si aplican. Usa solo slugs de la lista.

Reglas estrictas de tags (MUY IMPORTANTE):
- no_ficcion: SOLO memorias, biografías, crónica factual, divulgación, reportaje documental.
  NO uses no_ficcion para: entrevistas sobre novelas, reseñas de ficción, perfiles de autores de ficción.
- ficcion: novelas, relatos, reseñas de ficción, entrevistas sobre la OBRA DE FICCIÓN de un autor.
- ensayo_literario: ensayo, reflexión, crónica de ideas (incluso con ficción especulativa como eje).
- literatura_traducida / literatura_local: según origen del autor/obra respecto al mercado del medio.
- mundo_editorial: industria (fusiones, sellos, ventas, nombramientos editoriales).

Ejemplos correctos:
- Entrevista con Nina Lykke sobre su novela → ["ficcion", "literatura_traducida"]
- Memoria de un editor → ["no_ficcion", "mundo_editorial"]
- Ensayo especulativo sobre Barcelona 2131 → ["ensayo_literario", "ficcion"]
- Venta de derechos de traducción → ["derechos_traducciones", "mundo_editorial"]

Ejemplos incorrectos (evitar):
- Reseña o entrevista sobre novela → NO marcar no_ficcion
- Noticia de premio literario → ferias_premios, no no_ficcion salvo que sea biografía del ganador

Alcance editorial (en_alcance = true) — INCLUIR:
- Libros, novelas, poesía, ensayo literario o cultural con eje en libros/lectura
- Industria editorial: editoriales, imprentas, distribución, derechos, traducciones, ventas
- Autores, premios literarios, ferias del libro, reseñas de libros
- Debate literario, canon, crítica literaria, memoria editorial

Fuera de alcance (en_alcance = false) — EXCLUIR aunque el medio sea Tier 1:
- Música, conciertos, álbumes, festivales musicales
- Cine, series, TV, streaming, estrenos audiovisuales
- Deportes, moda, gastronomía, videojuegos, tecnología general
- Cultura general sin vínculo claro con libros, lectura o industria editorial
- Política, economía o sociedad sin ángulo editorial/literario

Reglas de categoría:
- "ideas": ensayos, crónicas largas, reportajes de fondo, reflexión literaria o cultural con eje libros.
- "noticias": actualidad editorial, novedades, reseñas breves, industria.

Reglas de traducción (OBLIGATORIO):
- resumen_generado: SIEMPRE 2-4 líneas en castellano (español de España), aunque el original esté en otro idioma. Estilo píldora informativa: qué ha pasado, contexto mínimo, por qué interesa al lector editorial.
- titular_traducido: SIEMPRE titular claro en castellano. Si el original ya está en español, reescríbelo más claro si hace falta; nunca devuelvas null.

Reglas de relevance_score (1-5):
- Si en_alcance es false → relevance_score MÁXIMO 2 (normalmente 1).
- 5 = destacado: pieza imprescindible del día (ensayo de fondo, reportaje clave, noticia editorial de alto impacto)
- 4 = relevante: merece lectura, buen contexto literario/editorial
- 3 = secundario: interesante pero no prioritario
- 2 = marginal: poco relevante para el informe
- 1 = ruido: descartar

Factores que suben el score (solo si en_alcance = true):
- Medio Tier 1: suele merecer 4-5 si el contenido es sólido; Tier 2 parte de 3.
- Actualidad: prioriza piezas recientes sobre libros/eventos editoriales recientes.

Sé exigente con los 5: no más del 15% de artículos deberían ser 5.
Sé estricto con en_alcance: ante la duda sobre música/cine/cultura general, marca false."""


def load_system_prompt() -> str:
    prompt = SYSTEM_PROMPT_BASE
    if EDITORIAL_CRITERIA.exists():
        extra = EDITORIAL_CRITERIA.read_text(encoding="utf-8").strip()
        if extra:
            prompt += f"\n\n--- Criterios editoriales del usuario ---\n{extra}"
    return prompt


def build_user_message(
    *,
    titulo: str,
    resumen: str | None,
    medio: str,
    categoria_default: Categoria,
    idioma: str,
    medio_tier: int,
    fecha_publicacion: str | None,
) -> str:
    fecha_line = fecha_publicacion or "(desconocida)"
    return "\n".join(
        [
            f"Titular: {titulo}",
            f"Resumen: {resumen or '(sin resumen)'}",
            f"Fuente: {medio}",
            f"Tier del medio: {tier_label(medio_tier)}",
            f"Fecha de publicación: {fecha_line}",
            f"Categoría prevista: {categoria_default}",
            f"Idioma: {idioma}",
        ]
    )


@dataclass
class ClassificationResult:
    categoria: Categoria
    relevance_score: int
    resumen_generado: str
    titular_traducido: str | None
    tags: list[str]
    en_alcance: bool = True


def _parse_tags(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    return validate_tags([str(t).strip() for t in raw if t])[:3]


def parse_response(text: str) -> ClassificationResult:
    cleaned = re.sub(r"```json\n?|```", "", text).strip()
    data = json.loads(cleaned)
    score = int(data["relevance_score"])
    score = max(1, min(5, score))
    categoria = data["categoria"]
    if categoria not in ("ideas", "noticias"):
        raise ValueError(f"Invalid categoria: {categoria}")
    titular = str(data.get("titular_traducido", "")).strip() or None
    en_alcance = bool(data.get("en_alcance", True))
    if not en_alcance:
        score = min(score, 2)
    return ClassificationResult(
        categoria=categoria,
        relevance_score=score,
        resumen_generado=str(data["resumen_generado"]).strip(),
        titular_traducido=titular,
        tags=_parse_tags(data.get("tags")),
        en_alcance=en_alcance,
    )


def finalize_result(
    *,
    titulo: str,
    resumen: str | None,
    result: ClassificationResult,
) -> ClassificationResult:
    result = ClassificationResult(
        categoria=result.categoria,
        relevance_score=result.relevance_score,
        resumen_generado=result.resumen_generado,
        titular_traducido=result.titular_traducido,
        tags=refine_tags(
            titulo=titulo,
            resumen=resumen,
            resumen_generado=result.resumen_generado,
            tags=result.tags,
        ),
        en_alcance=result.en_alcance,
    )
    if not is_editorial_scope(
        titulo=titulo,
        titular_traducido=result.titular_traducido,
        resumen=resumen,
        resumen_generado=result.resumen_generado,
    ):
        result = ClassificationResult(
            categoria=result.categoria,
            relevance_score=min(result.relevance_score, 2),
            resumen_generado=result.resumen_generado,
            titular_traducido=result.titular_traducido,
            tags=result.tags,
            en_alcance=False,
        )
    return result
