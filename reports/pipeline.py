"""Unified editorial pipeline: classify → filter → prioritize → report."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from ai.classify import classify_all_pending
from db.connection import get_connection
from db.models import ReportFilter
from reports.dates import publication_since_iso
from reports.generator import (
    ReportResult,
    _count_country_candidates,
    _count_tag_candidates,
    _resolve_window,
    build_report,
)
from reports.session import ReportSession

logger = logging.getLogger(__name__)

_BATCH_SIZE = 20
_MAX_BATCHES = 60
_TELEGRAM_CLASSIFY_CAP = 1


def _pending_in_window(
    report_filter: ReportFilter | None,
    since: datetime,
    *,
    date_by_publication: bool,
    mode: str = "informe",
) -> int:
    since_iso = publication_since_iso(since)
    if mode == "informe_hoy":
        with get_connection() as conn:
            return conn.execute(
                """
                SELECT COUNT(*) FROM articulos
                WHERE procesado = 0
                  AND fecha_publicacion IS NOT NULL AND fecha_publicacion != ''
                  AND fecha_publicacion >= ?
                """,
                (since_iso,),
            ).fetchone()[0]
    if mode == "informe" and not report_filter:
        with get_connection() as conn:
            return conn.execute(
                """
                SELECT COUNT(*) FROM articulos
                WHERE procesado = 0 AND fecha_ingesta >= ?
                """,
                (since_iso,),
            ).fetchone()[0]
    if report_filter and (report_filter.pais or report_filter.region):
        _, pending, _ = _count_country_candidates(
            report_filter,
            since,
            date_by_publication=date_by_publication,
        )
        return pending
    if report_filter and report_filter.tags:
        _, _, _, pending = _count_tag_candidates(
            report_filter,
            since,
            date_by_publication=date_by_publication,
        )
        return pending
    return 0


def _max_classify_batches(pending: int) -> int:
    if pending <= 0:
        return 0
    needed = (pending + _BATCH_SIZE - 1) // _BATCH_SIZE + 1
    return min(_MAX_BATCHES, needed)


def build_editorial_report(
    mode: str = "informe",
    report_filter: ReportFilter | None = None,
    *,
    continuation: ReportSession | None = None,
    chat_id: str | None = None,
    classify_before_report: bool = True,
    max_classify_batches: int | None = None,
) -> ReportResult:
    """
    Run the full editorial pipeline before generating a report.

    1. Classification agent (Claude): score, en_alcance, translation
    2. Report generator: editorial filter → prioritization → formatting

    Skips classification only for /informe_mas continuations.
    """
    if classify_before_report and continuation is None:
        since, _, resolved_mode = _resolve_window(mode, report_filter)
        use_pub_date = resolved_mode in ("informe_pais", "informe_hoy")
        pending = _pending_in_window(
            report_filter,
            since,
            date_by_publication=use_pub_date,
            mode=resolved_mode,
        )
        max_batches = _max_classify_batches(pending)
        if max_classify_batches is not None:
            max_batches = min(max_batches, max_classify_batches)
        if max_batches > 0:
            stats = classify_all_pending(
                report_filter=report_filter,
                since_iso=since.astimezone(ZoneInfo("UTC")).isoformat(),
                date_by_publication=use_pub_date,
                batch_size=_BATCH_SIZE,
                max_batches=max_batches,
            )
            logger.info(
                "Pipeline classify: pending=%d batches=%d classified=%d failed=%d remaining=%d",
                pending,
                max_batches,
                stats["classified"],
                stats["failed"],
                stats["remaining"],
            )
        else:
            logger.info("Pipeline classify: skipped (pending=%d)", pending)

    report = build_report(
        mode=mode,
        report_filter=report_filter,
        continuation=continuation,
        chat_id=chat_id,
    )
    logger.info(
        "Pipeline report mode=%s matched=%d shown=%d",
        report.mode,
        report.total_matched,
        len(report.article_ids),
    )
    return report
