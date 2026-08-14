"""Anthropic classification and summarization."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass

import anthropic

from ai.editorial_filter import is_editorial_scope
from bot.config import EDITORIAL_CRITERIA, settings
from db.connection import get_connection
from db.models import Categoria, ReportFilter
from medios_tiers import get_tier, tier_label

logger = logging.getLogger(__name__)

from reports.tags import validate_tags

MODEL = "claude-sonnet-5"
FALLBACK_MODEL = "claude-haiku-4-5"
_API_AUTH_FAILED = False

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


def _load_system_prompt() -> str:
    prompt = SYSTEM_PROMPT_BASE
    if EDITORIAL_CRITERIA.exists():
        extra = EDITORIAL_CRITERIA.read_text(encoding="utf-8").strip()
        if extra:
            prompt += f"\n\n--- Criterios editoriales del usuario ---\n{extra}"
    return prompt


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


def _parse_response(text: str) -> ClassificationResult:
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


def classify_offline(
    *,
    titulo: str,
    resumen: str | None,
    categoria_default: Categoria,
    idioma: str,
    reason: str = "missing",
) -> ClassificationResult:
    """Fallback when ANTHROPIC_API_KEY is not configured or rejected."""
    in_scope = is_editorial_scope(
        titulo=titulo,
        resumen=resumen,
    )
    if idioma != "es":
        if reason == "auth":
            summary = (
                "Resumen no disponible: ANTHROPIC_API_KEY inválida o expirada. "
                "Crea una clave nueva en console.anthropic.com, actualiza .env "
                "y ejecuta reclassify_untranslated.py."
            )
        else:
            summary = (
                "Resumen no disponible en castellano (clasificación offline). "
                "Configura ANTHROPIC_API_KEY y ejecuta reclassify_untranslated.py."
            )
        titular = f"[{idioma.upper()}] {titulo[:120]}"
    else:
        summary = (resumen or titulo)[:400]
        if len(summary) < 20:
            summary = f"{titulo}. Artículo recopilado del feed del medio."
        titular = titulo

    score = 3 if in_scope else 2
    return ClassificationResult(
        categoria=categoria_default,
        relevance_score=score,
        resumen_generado=summary,
        titular_traducido=titular if idioma != "es" else None,
        tags=[],
        en_alcance=in_scope,
    )


def classify_article(
    *,
    titulo: str,
    resumen: str | None,
    medio: str,
    categoria_default: Categoria,
    idioma: str,
    medio_tier: int = 2,
    fecha_publicacion: str | None = None,
) -> ClassificationResult:
    global _API_AUTH_FAILED

    if not settings.anthropic_api_key or _API_AUTH_FAILED:
        if not settings.anthropic_api_key:
            logger.warning(
                "ANTHROPIC_API_KEY missing — using offline classification"
            )
        return classify_offline(
            titulo=titulo,
            resumen=resumen,
            categoria_default=categoria_default,
            idioma=idioma,
            reason="missing",
        )

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    fecha_line = fecha_publicacion or "(desconocida)"
    user_msg = "\n".join(
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

    for model in (MODEL, FALLBACK_MODEL):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=600,
                system=_load_system_prompt(),
                messages=[{"role": "user", "content": user_msg}],
            )
            block = next(b for b in response.content if b.type == "text")
            result = _parse_response(block.text)
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
        except anthropic.AuthenticationError as exc:
            _API_AUTH_FAILED = True
            logger.error(
                "ANTHROPIC_API_KEY inválida o revocada; el pipeline continuará "
                "con clasificación offline. Actualiza .env y reinicia el bot.",
                exc_info=exc,
            )
            return classify_offline(
                titulo=titulo,
                resumen=resumen,
                categoria_default=categoria_default,
                idioma=idioma,
                reason="auth",
            )
        except anthropic.BadRequestError as exc:
            if "credit balance" in str(exc).lower():
                _API_AUTH_FAILED = True
                logger.error(
                    "Créditos de Anthropic agotados; el pipeline continuará "
                    "con clasificación offline (sin tags). Recarga créditos en "
                    "console.anthropic.com y ejecuta /reclasificar.",
                    exc_info=exc,
                )
                return classify_offline(
                    titulo=titulo,
                    resumen=resumen,
                    categoria_default=categoria_default,
                    idioma=idioma,
                    reason="auth",
                )
            raise
        except anthropic.NotFoundError:
            continue
        except anthropic.APIError:
            if model == FALLBACK_MODEL:
                raise
            continue

    raise RuntimeError("Classification failed for all models")


def classify_pending(
    limit: int = 50,
    delay_seconds: float = 0.2,
    *,
    report_filter: ReportFilter | None = None,
    since_iso: str | None = None,
    date_by_publication: bool = False,
) -> dict[str, int]:
    stats = {"classified": 0, "failed": 0, "remaining": 0}
    use_api = bool(settings.anthropic_api_key)
    conditions = ["a.procesado = 0"]
    params: list[object] = []
    if since_iso:
        date_col = (
            "COALESCE(NULLIF(a.fecha_publicacion, ''), a.fecha_ingesta)"
            if date_by_publication
            else "a.fecha_ingesta"
        )
        conditions.append(f"{date_col} >= ?")
        params.append(since_iso)
    if report_filter and report_filter.pais:
        conditions.append("m.pais = ?")
        params.append(report_filter.pais)
    elif report_filter and report_filter.region:
        conditions.append("m.region = ?")
        params.append(report_filter.region)
    where_clause = " AND ".join(conditions)

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT a.id, a.titulo_original, a.resumen_raw, a.categoria, a.idioma,
                   a.fecha_publicacion, m.nombre AS medio_nombre,
                   m.categoria_default, m.tier AS medio_tier
            FROM articulos a
            JOIN medios m ON m.id = a.medio_id
            WHERE {where_clause}
            ORDER BY a.fecha_ingesta DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()

        for i, row in enumerate(rows):
            if use_api and not _API_AUTH_FAILED and i > 0 and delay_seconds > 0:
                time.sleep(delay_seconds)
            try:
                result = classify_article(
                    titulo=row["titulo_original"],
                    resumen=row["resumen_raw"],
                    medio=row["medio_nombre"],
                    categoria_default=row["categoria_default"],
                    idioma=row["idioma"],
                    medio_tier=get_tier(row["medio_nombre"], row["categoria_default"]),
                    fecha_publicacion=row["fecha_publicacion"],
                )
                conn.execute(
                    """
                    UPDATE articulos SET
                        categoria = ?,
                        relevance_score = ?,
                        resumen_generado = ?,
                        titular_traducido = ?,
                        tags = ?,
                        procesado = 1
                    WHERE id = ?
                    """,
                    (
                        result.categoria,
                        result.relevance_score,
                        result.resumen_generado,
                        result.titular_traducido,
                        json.dumps(result.tags),
                        row["id"],
                    ),
                )
                conn.commit()
                stats["classified"] += 1
            except Exception as exc:
                logger.exception("Failed classifying article %s", row["id"])
                stats["failed"] += 1

        remaining = conn.execute(
            f"""
            SELECT COUNT(*) FROM articulos a
            JOIN medios m ON m.id = a.medio_id
            WHERE {where_clause}
            """,
            params,
        ).fetchone()[0]
        stats["remaining"] = remaining

    return stats


def classify_all_pending(
    *,
    batch_size: int = 30,
    max_batches: int = 20,
    delay_seconds: float = 0.2,
    report_filter: ReportFilter | None = None,
    since_iso: str | None = None,
    date_by_publication: bool = False,
) -> dict[str, int]:
    """Classify all pending articles in batches (for informe / cierre)."""
    totals = {"classified": 0, "failed": 0, "remaining": 0, "batches": 0}
    for _ in range(max_batches):
        stats = classify_pending(
            limit=batch_size,
            delay_seconds=delay_seconds,
            report_filter=report_filter,
            since_iso=since_iso,
            date_by_publication=date_by_publication,
        )
        totals["batches"] += 1
        totals["classified"] += stats["classified"]
        totals["failed"] += stats["failed"]
        totals["remaining"] = stats["remaining"]
        if stats["classified"] == 0 or stats["remaining"] == 0:
            break
    return totals
