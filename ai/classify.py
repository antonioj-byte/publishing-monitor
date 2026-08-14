"""Article classification via Gemini or Anthropic."""

from __future__ import annotations

import json
import logging
import time

import anthropic

from ai.gemini_client import generate_json, verify_gemini_api
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

# Anthropic models (fallback provider)
ANTHROPIC_MODEL = "claude-haiku-4-5"
ANTHROPIC_FALLBACK_MODEL = "claude-sonnet-5"

# Backward compatibility for health_check / bot_status
def active_model() -> str:
    if settings.classify_provider == "gemini":
        return settings.gemini_model
    return ANTHROPIC_MODEL


def active_fallback_model() -> str:
    if settings.classify_provider == "gemini":
        return settings.gemini_fallback_model
    return ANTHROPIC_FALLBACK_MODEL


MODEL = ANTHROPIC_MODEL
FALLBACK_MODEL = ANTHROPIC_FALLBACK_MODEL

_API_AUTH_FAILED = False


def active_provider() -> str:
    return settings.classify_provider


def reset_api_auth_state() -> None:
    global _API_AUTH_FAILED
    _API_AUTH_FAILED = False


def verify_classify_api() -> None:
    """Raise RuntimeError if the configured classify API is unavailable."""
    reset_api_auth_state()
    if settings.classify_provider == "gemini":
        verify_gemini_api()
    else:
        verify_anthropic_api()


def verify_anthropic_api() -> None:
    """Raise RuntimeError if Anthropic cannot classify (key, credits, models)."""
    reset_api_auth_state()
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY no configurada. Añádela en Railway → Variables."
        )

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    last_error: Exception | None = None
    for model in (ANTHROPIC_MODEL, ANTHROPIC_FALLBACK_MODEL):
        try:
            client.messages.create(
                model=model,
                max_tokens=20,
                messages=[{"role": "user", "content": "Responde solo: ok"}],
            )
            return
        except anthropic.AuthenticationError as exc:
            raise RuntimeError(
                "ANTHROPIC_API_KEY inválida. Renueva la clave en console.anthropic.com."
            ) from exc
        except anthropic.BadRequestError as exc:
            if "credit balance" in str(exc).lower():
                raise RuntimeError(
                    "Créditos de Anthropic agotados. Recarga en "
                    "console.anthropic.com → Plans & Billing."
                ) from exc
            raise RuntimeError(f"Anthropic rechazó la petición: {exc}") from exc
        except anthropic.NotFoundError as exc:
            last_error = exc
            continue
        except anthropic.APIError as exc:
            last_error = exc
            if model == ANTHROPIC_FALLBACK_MODEL:
                raise RuntimeError(f"Anthropic API error: {exc}") from exc
            continue

    raise RuntimeError(f"Ningún modelo Anthropic disponible: {last_error}")


def _api_unavailable_error(reason: str) -> RuntimeError:
    if settings.classify_provider == "gemini":
        return RuntimeError(
            "Gemini API no disponible para reclasificación con tags "
            f"({reason}). Revisa GOOGLE_API_KEY en Railway."
        )
    return RuntimeError(
        "Anthropic API no disponible para reclasificación con tags "
        f"({reason}). Revisa ANTHROPIC_API_KEY y créditos en console.anthropic.com."
    )


def _has_classify_api() -> bool:
    return settings.has_classify_api()


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
    provider = settings.classify_provider
    if idioma != "es":
        if reason == "auth":
            if provider == "gemini":
                summary = (
                    "Resumen no disponible: GOOGLE_API_KEY inválida o sin cuota. "
                    "Actualiza .env y ejecuta /retag."
                )
            else:
                summary = (
                    "Resumen no disponible: API key inválida o expirada. "
                    "Actualiza .env y ejecuta /retag."
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
        titular_traducido=titular if idioma != "es" else None,
        tags=[],
        en_alcance=in_scope,
    )


def _classify_with_gemini(
    *,
    user_msg: str,
    titulo: str,
    resumen: str | None,
) -> ClassificationResult:
    system_prompt = load_system_prompt()
    last_error: Exception | None = None
    for model in (settings.gemini_model, settings.gemini_fallback_model):
        try:
            raw = generate_json(system_prompt=system_prompt, user_msg=user_msg, model=model)
            return finalize_result(
                titulo=titulo,
                resumen=resumen,
                result=parse_response(raw),
            )
        except Exception as exc:
            last_error = exc
            logger.warning("Gemini model %s failed: %s", model, exc)
            continue
    raise RuntimeError(f"Gemini classification failed: {last_error}")


def _classify_with_anthropic(
    *,
    user_msg: str,
    titulo: str,
    resumen: str | None,
) -> ClassificationResult:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    system_prompt = load_system_prompt()
    for model in (ANTHROPIC_MODEL, ANTHROPIC_FALLBACK_MODEL):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=600,
                system=system_prompt,
                messages=[{"role": "user", "content": user_msg}],
            )
            block = next(b for b in response.content if b.type == "text")
            return finalize_result(
                titulo=titulo,
                resumen=resumen,
                result=parse_response(block.text),
            )
        except anthropic.NotFoundError:
            continue
        except anthropic.APIError:
            if model == ANTHROPIC_FALLBACK_MODEL:
                raise
            continue
    raise RuntimeError("Anthropic classification failed for all models")


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
    global _API_AUTH_FAILED

    if not _has_classify_api() or _API_AUTH_FAILED:
        if not allow_offline:
            reason = "sin clave" if not _has_classify_api() else "API caída"
            raise _api_unavailable_error(reason)
        if not _has_classify_api():
            logger.warning(
                "No classify API key for provider=%s — using offline classification",
                settings.classify_provider,
            )
        return classify_offline(
            titulo=titulo,
            resumen=resumen,
            categoria_default=categoria_default,
            idioma=idioma,
            reason="missing",
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

    try:
        if settings.classify_provider == "gemini":
            return _classify_with_gemini(
                user_msg=user_msg,
                titulo=titulo,
                resumen=resumen,
            )
        return _classify_with_anthropic(
            user_msg=user_msg,
            titulo=titulo,
            resumen=resumen,
        )
    except anthropic.AuthenticationError as exc:
        _API_AUTH_FAILED = True
        logger.error("Anthropic auth failed — offline fallback", exc_info=exc)
        if not allow_offline:
            raise _api_unavailable_error("clave inválida") from exc
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
            logger.error("Anthropic credits exhausted", exc_info=exc)
            if not allow_offline:
                raise _api_unavailable_error("créditos agotados") from exc
            return classify_offline(
                titulo=titulo,
                resumen=resumen,
                categoria_default=categoria_default,
                idioma=idioma,
                reason="auth",
            )
        raise
    except Exception as exc:
        err = str(exc).lower()
        if settings.classify_provider == "gemini" and (
            "api key" in err or "quota" in err or "billing" in err or "401" in err
        ):
            _API_AUTH_FAILED = True
            logger.error("Gemini API failed — offline fallback", exc_info=exc)
            if not allow_offline:
                raise _api_unavailable_error(str(exc)) from exc
            return classify_offline(
                titulo=titulo,
                resumen=resumen,
                categoria_default=categoria_default,
                idioma=idioma,
                reason="auth",
            )
        raise


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
