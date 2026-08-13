"""Anthropic classification and summarization."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass

import anthropic

from bot.config import EDITORIAL_CRITERIA, settings
from db.connection import get_connection
from db.models import Categoria

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"
FALLBACK_MODEL = "claude-3-5-haiku-20241022"

SYSTEM_PROMPT_BASE = """Eres editor de un informe diario sobre cultura, literatura y el mundo editorial.

Para cada artículo recibirás titular, resumen, fuente, categoría prevista e idioma.

Responde SOLO con JSON válido:
{
  "categoria": "ideas" | "noticias",
  "relevance_score": number,
  "resumen_generado": string,
  "titular_traducido": string
}

Reglas de categoría:
- "ideas": ensayos, crónicas largas, reportajes de fondo, reflexión cultural.
- "noticias": actualidad, novedades, reseñas breves, industria editorial.

Reglas de traducción (OBLIGATORIO):
- resumen_generado: SIEMPRE 2-4 líneas en castellano (español de España), aunque el original esté en otro idioma.
- titular_traducido: SIEMPRE titular claro en castellano. Si el original ya está en español, reescríbelo más claro si hace falta; nunca devuelvas null.

Reglas de relevance_score (1-5):
- 5 = destacado: pieza imprescindible del día (ensayo de fondo, reportaje clave, noticia editorial de alto impacto)
- 4 = relevante: merece lectura, buen contexto cultural/editorial
- 3 = secundario: interesante pero no prioritario
- 2 = marginal: poco relevante para el informe
- 1 = ruido: descartar (farándula, relleno, off-topic)

Sé exigente con los 5: no más del 15% de artículos deberían ser 5."""


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


def _parse_response(text: str) -> ClassificationResult:
    cleaned = re.sub(r"```json\n?|```", "", text).strip()
    data = json.loads(cleaned)
    score = int(data["relevance_score"])
    score = max(1, min(5, score))
    categoria = data["categoria"]
    if categoria not in ("ideas", "noticias"):
        raise ValueError(f"Invalid categoria: {categoria}")
    titular = str(data.get("titular_traducido", "")).strip() or None
    return ClassificationResult(
        categoria=categoria,
        relevance_score=score,
        resumen_generado=str(data["resumen_generado"]).strip(),
        titular_traducido=titular,
    )


def classify_offline(
    *,
    titulo: str,
    resumen: str | None,
    categoria_default: Categoria,
    idioma: str,
) -> ClassificationResult:
    """Fallback when ANTHROPIC_API_KEY is not configured."""
    summary = (resumen or titulo)[:400]
    if len(summary) < 20:
        summary = f"{titulo}. Artículo recopilado del feed del medio."
    titular = titulo if idioma == "es" else titulo
    return ClassificationResult(
        categoria=categoria_default,
        relevance_score=3,
        resumen_generado=summary,
        titular_traducido=None if idioma == "es" else titular,
    )


def classify_article(
    *,
    titulo: str,
    resumen: str | None,
    medio: str,
    categoria_default: Categoria,
    idioma: str,
) -> ClassificationResult:
    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY missing — using offline classification")
        return classify_offline(
            titulo=titulo,
            resumen=resumen,
            categoria_default=categoria_default,
            idioma=idioma,
        )

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    user_msg = "\n".join(
        [
            f"Titular: {titulo}",
            f"Resumen: {resumen or '(sin resumen)'}",
            f"Fuente: {medio}",
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
            return _parse_response(block.text)
        except anthropic.AuthenticationError as exc:
            raise RuntimeError(
                "ANTHROPIC_API_KEY inválida o revocada. "
                "Genera una nueva en console.anthropic.com y actualiza .env"
            ) from exc
        except anthropic.NotFoundError:
            continue
        except anthropic.APIError:
            if model == FALLBACK_MODEL:
                raise
            continue

    raise RuntimeError("Classification failed for all models")


def classify_pending(limit: int = 50, delay_seconds: float = 0.2) -> dict[str, int]:
    stats = {"classified": 0, "failed": 0, "remaining": 0}
    use_api = bool(settings.anthropic_api_key)

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT a.id, a.titulo_original, a.resumen_raw, a.categoria, a.idioma,
                   m.nombre AS medio_nombre, m.categoria_default
            FROM articulos a
            JOIN medios m ON m.id = a.medio_id
            WHERE a.procesado = 0
            ORDER BY a.fecha_ingesta DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        for i, row in enumerate(rows):
            if use_api and i > 0 and delay_seconds > 0:
                time.sleep(delay_seconds)
            try:
                result = classify_article(
                    titulo=row["titulo_original"],
                    resumen=row["resumen_raw"],
                    medio=row["medio_nombre"],
                    categoria_default=row["categoria_default"],
                    idioma=row["idioma"],
                )
                conn.execute(
                    """
                    UPDATE articulos SET
                        categoria = ?,
                        relevance_score = ?,
                        resumen_generado = ?,
                        titular_traducido = ?,
                        procesado = 1
                    WHERE id = ?
                    """,
                    (
                        result.categoria,
                        result.relevance_score,
                        result.resumen_generado,
                        result.titular_traducido,
                        row["id"],
                    ),
                )
                conn.commit()
                stats["classified"] += 1
            except Exception as exc:
                logger.exception("Failed classifying article %s", row["id"])
                stats["failed"] += 1

        remaining = conn.execute(
            "SELECT COUNT(*) FROM articulos WHERE procesado = 0"
        ).fetchone()[0]
        stats["remaining"] = remaining

    return stats
