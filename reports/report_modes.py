"""Explicit report modes for reports/generator.py and reports/prioritize.py.

Mode values intentionally match the existing string constants used across
bot commands, `ReportSession`, and scripts (`ReportMode` is a `str` subclass,
so `mode == "informe_pais"` comparisons elsewhere keep working unchanged).
This only centralizes the *behavioral* differences between modes so
generator.py doesn't scatter ad hoc string comparisons.
"""

from __future__ import annotations

from enum import Enum


class ReportMode(str, Enum):
    """How a report should be windowed, dated, and prioritized.

    DAILY_DIGEST: default `/informe` since the last cierre — breaking-news
        style. Strict prioritization threshold, one article per event.
    CATALOG: `/informe <días> <tag|país>` — multi-day browsing. All matched
        articles are included; recency is scaled across the full window
        instead of a 24-48h cliff, and events are not collapsed.
    TODAY: `/informe_hoy` — only articles published today (strict
        publication date, no ingestion-date fallback).
    CONTINUATION: `/informe_mas` — paginated continuation of a previous
        report; reuses the original report's ordering, no reclassification.
    """

    DAILY_DIGEST = "informe"
    CATALOG = "informe_pais"
    TODAY = "informe_hoy"
    CONTINUATION = "informe_mas"

    @classmethod
    def from_str(cls, value: str) -> "ReportMode":
        try:
            return cls(value)
        except ValueError:
            return cls.DAILY_DIGEST

    @property
    def is_catalog(self) -> bool:
        """Multi-day tag/country browsing — not a breaking-news digest."""
        return self is ReportMode.CATALOG

    @property
    def uses_publication_date(self) -> bool:
        """Filter/order by publication date (ingestion-date fallback allowed)."""
        return self in (ReportMode.CATALOG, ReportMode.TODAY, ReportMode.DAILY_DIGEST)

    @property
    def strict_publication_date(self) -> bool:
        """Exclude articles missing a real publication date entirely."""
        return self in (ReportMode.TODAY, ReportMode.DAILY_DIGEST)
