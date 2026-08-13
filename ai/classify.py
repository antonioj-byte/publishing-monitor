"""Anthropic classification and summarization."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass

import anthropic

from bot.config import settings
from db.connection import get_connection
from db.models import Categoria

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"
FALLBACK_MODEL = "claude-3-5-sonnet-20241022"

SYSTEM_PROMPT = """Eres editor de un informe diario sobre cultura, literatura y el mundo editorial.

Para cada artículo recibirás titular, resumen, fuente, categoría prevista e idioma.

Responde SOLO con JSON válido:
{
  "categoria": "ideas" | "noticias",
  "relevance_score": number,
  "resumen_generado": string,
  "titular_traducido": string | null
}

Reglas:
- categoria "ideas": ensayos, crónicas largas, reportajes de fondo, reflexión cultural.
- categoria "noticias": actualidad, novedades, reseñas breves, industria editorial.
- Confirma la categoría prevista salvo error claro del medio.
- relevance_score 1-5: 5=muy relevante para lector cultural/editorial; 1=ruido.
- resumen_generado: 2-4 líneas en español, informativas.
- titular_traducido: titular claro en español si el original no está en español; null si ya está en español."""


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
    titular = data.get("titular_traducido")
    if titular is not None:
        titular = str(titular).strip() or None
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
                system=SYSTEM_PROMPT,
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
