"""Persist report sessions for /informe_mas continuation."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from bot.config import settings
from db.connection import get_connection
from db.models import ReportFilter


@dataclass
class ReportSession:
    chat_id: str
    mode: str
    since_iso: str
    include_sent: bool
    report_filter: ReportFilter | None
    article_ids: list[int]
    cursor: int
    trends_included: bool


def _serialize_filter(report_filter: ReportFilter | None) -> str | None:
    if not report_filter:
        return None
    return json.dumps(asdict(report_filter))


def _deserialize_filter(raw: str | None) -> ReportFilter | None:
    if not raw:
        return None
    data = json.loads(raw)
    return ReportFilter(**data)


def save_session(session: ReportSession) -> None:
    now = datetime.now(ZoneInfo(settings.timezone)).isoformat()
    with get_connection() as conn:
        conn.execute("DELETE FROM informe_sesiones WHERE chat_id = ?", (session.chat_id,))
        conn.execute(
            """
            INSERT INTO informe_sesiones (
                chat_id, mode, since_iso, include_sent, report_filter,
                article_ids, cursor, trends_included, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.chat_id,
                session.mode,
                session.since_iso,
                1 if session.include_sent else 0,
                _serialize_filter(session.report_filter),
                json.dumps(session.article_ids),
                session.cursor,
                1 if session.trends_included else 0,
                now,
            ),
        )
        conn.commit()


def load_session(chat_id: str) -> ReportSession | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT chat_id, mode, since_iso, include_sent, report_filter,
                   article_ids, cursor, trends_included
            FROM informe_sesiones
            WHERE chat_id = ?
            """,
            (chat_id,),
        ).fetchone()
    if not row:
        return None
    return ReportSession(
        chat_id=row["chat_id"],
        mode=row["mode"],
        since_iso=row["since_iso"],
        include_sent=bool(row["include_sent"]),
        report_filter=_deserialize_filter(row["report_filter"]),
        article_ids=json.loads(row["article_ids"]),
        cursor=row["cursor"],
        trends_included=bool(row["trends_included"]),
    )


def clear_session(chat_id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM informe_sesiones WHERE chat_id = ?", (chat_id,))
        conn.commit()
