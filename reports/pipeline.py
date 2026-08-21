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
    _count_medio_candidates,
    _count_tag_candidates,
    _resolve_window,
    build_report,
)
from reports.pipeline_dates import date_flags_for_mode, pending_date_sql
from reports.session import ReportSession

logger = logging.getLogger(__name__)

_BATCH_SIZE = 20
_MAX_BATCHES = 60
_FILTERED_CLASSIFY_BATCH_CAP = 5  # up to 100 articles per país/tag/hoy informe
_DAILY_CLASSIFY_BATCH_CAP = 5  # up to 100 articles for /informe diario (fast path)


def _pending_in_window(
    report_filter: ReportFilter | None,
    since: datetime,
    *,
    date_by_publication: bool,
    strict_publication: bool = False,
    mode: str = "informe",
) -> int:
    since_iso = publication_since_iso(since)
    date_expr, pub_filter = pending_date_sql(
        date_by_publication=date_by_publication,
        strict_publication=strict_publication,
    )

    if mode == "informe_hoy" or (mode == "informe" and not report_filter):
        with get_connection() as conn:
            return conn.execute(
                f"""
                SELECT COUNT(*) FROM articulos a
                WHERE a.procesado = 0
                  {pub_filter}
                  AND {date_expr} >= ?
                """,
                (since_iso,),
            ).fetchone()[0]

    if report_filter and report_filter.medio_nombre:
        _, pending, _ = _count_medio_candidates(
            report_filter,
            since,
            date_by_publication=date_by_publication,
            strict_publication=strict_publication,
        )
        return pending
    if report_filter and (report_filter.pais or report_filter.region):
        _, pending, _ = _count_country_candidates(
            report_filter,
            since,
            date_by_publication=date_by_publication,
            strict_publication=strict_publication,
        )
        return pending
    if report_filter and report_filter.tags:
        _, _, _, pending = _count_tag_candidates(
            report_filter,
            since,
            date_by_publication=date_by_publication,
            strict_publication=strict_publication,
        )
        return pending
    return 0


def _max_classify_batches(pending: int) -> int:
    if pending <= 0:
        return 0
    needed = (pending + _BATCH_SIZE - 1) // _BATCH_SIZE + 1
    return min(_MAX_BATCHES, needed)


def _batches_for_filtered_pending(pending: int) -> int:
    """Batches needed to classify all pending in a país/tag/hoy window (capped)."""
    if pending <= 0:
        return 0
    needed = (pending + _BATCH_SIZE - 1) // _BATCH_SIZE
    return min(needed, _FILTERED_CLASSIFY_BATCH_CAP)


def _batches_for_daily_pending(pending: int) -> int:
    if pending <= 0:
        return 0
    needed = (pending + _BATCH_SIZE - 1) // _BATCH_SIZE
    return min(needed, _DAILY_CLASSIFY_BATCH_CAP)


def _should_classify_for_filter(mode: str, report_filter: ReportFilter | None) -> bool:
    if mode == "informe_hoy":
        return True
    if not report_filter:
        return False
    return bool(
        report_filter.pais
        or report_filter.region
        or report_filter.tags
        or report_filter.medio_nombre
    )


def build_editorial_report(
    mode: str = "informe",
    report_filter: ReportFilter | None = None,
    *,
    continuation: ReportSession | None = None,
    chat_id: str | None = None,
    classify_before_report: bool = True,
    max_classify_batches: int | None = None,
    use_embedding_prioritization: bool = True,
) -> ReportResult:
    """
    Run the full editorial pipeline before generating a report.

    1. Classification agent (Claude): score, en_alcance, translation
    2. Report generator: editorial filter → prioritization → formatting

    Skips classification only for /informe_mas continuations.
    """
    if continuation is None:
        since, _, resolved_mode = _resolve_window(mode, report_filter)
        use_pub_date, strict_pub = date_flags_for_mode(resolved_mode)
        pending = _pending_in_window(
            report_filter,
            since,
            date_by_publication=use_pub_date,
            strict_publication=strict_pub,
            mode=resolved_mode,
        )
        if classify_before_report:
            max_batches = _max_classify_batches(pending)
            if max_classify_batches is not None:
                max_batches = min(max_batches, max_classify_batches)
        elif pending > 0 and _should_classify_for_filter(resolved_mode, report_filter):
            max_batches = _batches_for_filtered_pending(pending)
            if max_classify_batches is not None:
                max_batches = min(max_batches, max_classify_batches)
        else:
            max_batches = 0
        if max_batches > 0:
            stats = classify_all_pending(
                report_filter=report_filter,
                since_iso=since.astimezone(ZoneInfo("UTC")).isoformat(),
                date_by_publication=use_pub_date,
                strict_publication_date=strict_pub,
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
        use_embedding_prioritization=use_embedding_prioritization,
    )
    logger.info(
        "Pipeline report mode=%s matched=%d shown=%d",
        report.mode,
        report.total_matched,
        len(report.article_ids),
    )
    return report


def classify_pending_for_daily_report(*, max_batches: int = 5) -> dict[str, int]:
    """Classify pending articles in the daily informe window (cierre / informe automático)."""
    since, _, resolved_mode = _resolve_window("informe", None)
    use_pub_date, strict_pub = date_flags_for_mode(resolved_mode)
    pending = _pending_in_window(
        None,
        since,
        date_by_publication=use_pub_date,
        strict_publication=strict_pub,
        mode=resolved_mode,
    )
    batches = min(_batches_for_daily_pending(pending), max(0, max_batches))
    if batches <= 0:
        return {"classified": 0, "failed": 0, "remaining": pending, "batches": 0}
    stats = classify_all_pending(
        since_iso=since.astimezone(ZoneInfo("UTC")).isoformat(),
        date_by_publication=use_pub_date,
        strict_publication_date=strict_pub,
        batch_size=_BATCH_SIZE,
        max_batches=batches,
    )
    logger.info(
        "Daily window classify: pending=%d batches=%d classified=%d remaining=%d",
        pending,
        batches,
        stats["classified"],
        stats["remaining"],
    )
    return stats
