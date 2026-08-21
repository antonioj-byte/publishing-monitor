"""Shared publication-date rules for pipeline, classify, and diagnostics."""

from __future__ import annotations

from reports.report_modes import ReportMode


def date_flags_for_mode(mode: str) -> tuple[bool, bool]:
    """Return (date_by_publication, strict_publication_date) for a report mode."""
    report_mode = ReportMode.from_str(mode)
    return report_mode.uses_publication_date, report_mode.strict_publication_date


def pending_date_sql(
    *,
    date_by_publication: bool,
    strict_publication: bool,
    alias: str = "a",
) -> tuple[str, str]:
    """Return (date_expression, extra_and_clause) for pending-article counts."""
    if not date_by_publication:
        return f"{alias}.fecha_ingesta", ""
    if strict_publication:
        return (
            f"{alias}.fecha_publicacion",
            f"AND {alias}.fecha_publicacion IS NOT NULL AND {alias}.fecha_publicacion != ''",
        )
    return (
        f"COALESCE(NULLIF({alias}.fecha_publicacion, ''), {alias}.fecha_ingesta)",
        "",
    )
