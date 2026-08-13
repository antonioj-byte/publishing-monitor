"""Unified editorial pipeline: classify → filter → prioritize → report."""

from __future__ import annotations

import logging

from ai.classify import classify_all_pending
from reports.generator import ReportResult, build_report
from db.models import ReportFilter
from reports.session import ReportSession

logger = logging.getLogger(__name__)


def build_editorial_report(
    mode: str = "informe",
    report_filter: ReportFilter | None = None,
    *,
    continuation: ReportSession | None = None,
    chat_id: str | None = None,
    classify_before_report: bool = True,
) -> ReportResult:
    """
    Run the full editorial pipeline before generating a report.

    1. Classification agent (Claude): score, en_alcance, translation
    2. Report generator: editorial filter → prioritization → formatting

    Skips classification only for /informe_mas continuations.
    """
    if classify_before_report and continuation is None:
        stats = classify_all_pending()
        logger.info(
            "Pipeline classify: %d classified, %d failed, %d remaining",
            stats["classified"],
            stats["failed"],
            stats["remaining"],
        )

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
