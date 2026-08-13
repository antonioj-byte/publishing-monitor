"""Tests for report delivery bookkeeping."""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.telegram_handlers import _send_continuation, _send_report
from reports.generator import ReportResult
from reports.session import ReportSession


def _update() -> SimpleNamespace:
    return SimpleNamespace(
        message=SimpleNamespace(reply_text=AsyncMock()),
        effective_chat=SimpleNamespace(id=123),
    )


class ReportDeliveryTests(unittest.TestCase):
    def test_truncated_first_page_marks_sent_without_advancing_cierre(self) -> None:
        update = _update()
        result = ReportResult(
            text="page one",
            article_ids=[1],
            mode="informe",
            has_more=True,
        )
        with (
            patch("bot.telegram_handlers.is_authorized", return_value=True),
            patch(
                "bot.telegram_handlers.build_editorial_report",
                return_value=result,
            ),
            patch("bot.telegram_handlers.mark_articles_sent") as mark,
            patch("bot.telegram_handlers.record_informe") as record,
        ):
            asyncio.run(_send_report(update, mode="informe", record=True))

        mark.assert_called_once_with([1])
        record.assert_not_called()

    def test_final_continuation_records_complete_snapshot(self) -> None:
        update = _update()
        session = ReportSession(
            chat_id="123",
            mode="informe",
            since_iso="2026-08-13T00:00:00+00:00",
            include_sent=False,
            report_filter=None,
            article_ids=[1, 2],
            cursor=1,
            trends_included=True,
        )
        result = ReportResult(
            text="page two",
            article_ids=[2],
            mode="informe_mas",
            has_more=False,
        )
        with (
            patch("bot.telegram_handlers.is_authorized", return_value=True),
            patch("bot.telegram_handlers.load_session", return_value=session),
            patch(
                "bot.telegram_handlers.build_editorial_report",
                return_value=result,
            ),
            patch("bot.telegram_handlers.mark_articles_sent") as mark,
            patch("bot.telegram_handlers.record_informe") as record,
        ):
            asyncio.run(_send_continuation(update))

        mark.assert_called_once_with([2])
        record.assert_called_once_with([1, 2], "manual")


if __name__ == "__main__":
    unittest.main()
