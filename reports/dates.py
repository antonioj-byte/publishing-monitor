"""Publication date parsing and filtering for reports."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def parse_publication_datetime(value: str | None) -> datetime | None:
    if not value or not str(value).strip():
        return None
    raw = str(value).strip()
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def publication_within_window(
    fecha_publicacion: str | None,
    since: datetime,
    *,
    until: datetime | None = None,
) -> bool:
    published = parse_publication_datetime(fecha_publicacion)
    if published is None:
        return False
    since_utc = since.astimezone(timezone.utc)
    if published < since_utc:
        return False
    if until is not None and published > until.astimezone(timezone.utc):
        return False
    return True


def publication_since_iso(since: datetime) -> str:
    return since.astimezone(timezone.utc).isoformat()


def catalog_window_start(days: int, now: datetime) -> datetime:
    """Inclusive calendar window for /informe N … (today counts as day 1).

    «Últimos 7 días» on Aug 21 → desde Aug 15 00:00 local, not Aug 14
    (``now - timedelta(days=7)`` would span 8 calendar days).
    """
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    span = max(1, days)
    return start_of_today - timedelta(days=span - 1)


def format_publication_display(
    fecha_publicacion: str | None,
    *,
    timezone_name: str = "Europe/Madrid",
    fallback_ingesta: str | None = None,
) -> str | None:
    """Human-readable publication date for Telegram (dd/mm/yyyy)."""
    dt = parse_publication_datetime(fecha_publicacion)
    label_prefix = "Publicado"
    if dt is None and fallback_ingesta:
        dt = parse_publication_datetime(fallback_ingesta)
        label_prefix = "Ingesta"
    if dt is None:
        return None
    local = dt.astimezone(ZoneInfo(timezone_name))
    return f"{label_prefix}: {local.strftime('%d/%m/%Y')}"
