"""Article classification via a configurable LLM provider (Gemini or Anthropic).

This module only orchestrates: retries, offline fallback, DB writes. Vendor
SDK calls live in ai/llm_provider.py.
"""

from __future__ import annotations

import json
import logging
import time

from ai.llm_provider import LLMAuthError, LLMQuotaError, get_provider
from ai.llm_shared import (
    ClassificationResult,
    build_user_message,
    finalize_result,
    load_system_prompt,
    parse_response,
)
from bot.config import settings
from db.connection import get_connection
from db.models import Categoria, ReportFilter
from medios_tiers import get_tier

logger = logging.getLogger(__name__)

_API_AUTH_FAILED = False
_API_FAILURE_REASON: str | None = None  # "auth" | "quota" | None

_IDIOMA_LABEL = {
    "en": "inglés",
    "fr": "francés",
    "de": "alemán",
    "it": "italiano",
    "pt": "portugués",
    "ca": "catalán",
    "nl": "neerlandés",
}

QUOTA_ORIGINAL_PREFIX = "⚠️ Sin créditos en"


def active_provider() -> str:
    return settings.classify_provider


def active_model() -> str:
    return get_provider(settings).primary_model


def reset_api_auth_state() -> None:
    global _API_AUTH_FAILED, _API_FAILURE_REASON
    _API_AUTH_FAILED = False
    _API_FAILURE_REASON = None


def verify_classify_api() -> None:
    """Raise RuntimeError if the configured classify API is unavailable."""
    reset_api_auth_state()
    get_provider(settings).verify_api()


def _api_unavailable_error(reason: str) -> RuntimeError:
    provider = get_provider(settings)
    return RuntimeError(
        f"{provider.label} no disponible para reclasificación con tags "
        f"({reason}). Revisa {provider.key_env_name} en Railway "
        f"({provider.setup_url})."
    )


def _has_classify_api() -> bool:
    return settings.has_classify_api()


def _provider_short_label() -> str:
    if settings.classify_provider == "gemini":
        return "Gemini"
    return get_provider(settings).label


def _original_language_body(titulo: str, resumen: str | None) -> str:
    body = (resumen or titulo).strip()
    if len(body) < 20:
        body = titulo
    return body[:400]


def classify_offline(
    *,
    titulo: str,
    resumen: str | None,
    categoria_default: Categoria,
    idioma: str,
    reason: str = "missing",
) -> ClassificationResult:
    """Fallback when no LLM API is configured or rejected."""
    from ai.editorial_filter import is_editorial_scope

    in_scope = is_editorial_scope(titulo=titulo, resumen=resumen)
    provider = get_provider(settings)

    if reason == "quota":
        lang_label = _IDIOMA_LABEL.get(idioma, idioma.upper())
        body = _original_language_body(titulo, resumen)
        if idioma == "es":
            summary = (
                f"{QUOTA_ORIGINAL_PREFIX} {_provider_short_label()}; "
                f"mostrando el texto del feed.\n\n{body}"
            )
            titular = titulo
        else:
            summary = (
                f"{QUOTA_ORIGINAL_PREFIX} {_provider_short_label()}; "
                f"mostrando texto original ({lang_label}).\n\n{body}"
            )
            titular = None
    elif idioma != "es":
        if reason == "auth":
            summary = (
                f"Resumen no disponible: {provider.key_env_name} inválida o sin "
                "cuota/créditos. Actualiza .env y ejecuta /retag."
            )
        else:
            summary = (
                "Resumen no disponible en castellano (clasificación offline). "
                "Configura la API de clasificación y ejecuta /retag."
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
        titular_traducido=titular if idioma != "es" and reason != "quota" else None,
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
    allow_offline: bool = True,
) -> ClassificationResult:
    global _API_AUTH_FAILED, _API_FAILURE_REASON

    if not _has_classify_api() or _API_AUTH_FAILED:
        if not allow_offline:
            reason = "sin clave" if not _has_classify_api() else "API caída"
            raise _api_unavailable_error(reason)
        if not _has_classify_api():
            logger.warning(
                "No classify API key for provider=%s — using offline classification",
                settings.classify_provider,
            )
        offline_reason = _API_FAILURE_REASON or "missing"
        return classify_offline(
            titulo=titulo,
            resumen=resumen,
            categoria_default=categoria_default,
            idioma=idioma,
            reason=offline_reason,
        )

    user_msg = build_user_message(
        titulo=titulo,
        resumen=resumen,
        medio=medio,
        categoria_default=categoria_default,
        idioma=idioma,
        medio_tier=medio_tier,
        fecha_publicacion=fecha_publicacion,
    )

    provider = get_provider(settings)
    system_prompt = load_system_prompt()
    try:
        raw = provider.generate_json(system_prompt=system_prompt, user_msg=user_msg)
        return finalize_result(
            titulo=titulo,
            resumen=resumen,
            result=parse_response(raw),
        )
    except LLMQuotaError as exc:
        _API_AUTH_FAILED = True
        _API_FAILURE_REASON = "quota"
        logger.error("%s quota failed — original-language fallback", provider.name, exc_info=exc)
        if not allow_offline:
            raise _api_unavailable_error(str(exc)) from exc
        return classify_offline(
            titulo=titulo,
            resumen=resumen,
            categoria_default=categoria_default,
            idioma=idioma,
            reason="quota",
        )
    except LLMAuthError as exc:
        _API_AUTH_FAILED = True
        _API_FAILURE_REASON = "auth"
        logger.error("%s auth failed — offline fallback", provider.name, exc_info=exc)
        if not allow_offline:
            raise _api_unavailable_error(str(exc)) from exc
        return classify_offline(
            titulo=titulo,
            resumen=resumen,
            categoria_default=categoria_default,
            idioma=idioma,
            reason="auth",
        )


def classify_pending(
    limit: int = 50,
    delay_seconds: float = 0.2,
    *,
    report_filter: ReportFilter | None = None,
    since_iso: str | None = None,
    date_by_publication: bool = False,
    require_tags: bool = False,
) -> dict[str, int]:
    stats = {"classified": 0, "failed": 0, "remaining": 0, "no_tags": 0}
    use_api = _has_classify_api()
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
    if report_filter and report_filter.medio_nombre:
        conditions.append("m.nombre = ?")
        params.append(report_filter.medio_nombre)
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
                    allow_offline=not require_tags,
                )
                if require_tags and not result.tags:
                    stats["no_tags"] += 1
                    stats["failed"] += 1
                    continue
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
            except Exception:
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
