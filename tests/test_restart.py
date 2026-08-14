"""Tests for in-process bot restart."""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from bot.restart_service import RestartMethod, detect_restart_method, restart_bot
from bot.telegram_handlers import reiniciar_command


class RestartDetectionTests(unittest.TestCase):
    def test_defaults_to_exec_when_no_supervisor(self) -> None:
        with (
            patch("bot.restart_service._systemd_service_active", return_value=False),
            patch("bot.restart_service._launchd_job_loaded", return_value=False),
        ):
            self.assertEqual(detect_restart_method(), RestartMethod.EXEC)

    def test_prefers_systemd_when_active(self) -> None:
        with patch("bot.restart_service._systemd_service_active", return_value=True):
            self.assertEqual(detect_restart_method(), RestartMethod.SYSTEMD)


class RestartHandlerTests(unittest.TestCase):
    def test_reiniciar_requires_authorization(self) -> None:
        update = SimpleNamespace(
            message=SimpleNamespace(reply_text=AsyncMock()),
            effective_chat=SimpleNamespace(id=999),
        )
        context = SimpleNamespace(application=MagicMock(), bot_data={})
        with patch("bot.telegram_handlers.is_authorized", return_value=False):
            asyncio.run(reiniciar_command(update, context))
        update.message.reply_text.assert_awaited_once()

    def test_reiniciar_schedules_restart(self) -> None:
        update = SimpleNamespace(
            message=SimpleNamespace(reply_text=AsyncMock()),
            effective_chat=SimpleNamespace(id=123),
        )
        app = MagicMock()
        app.bot_data = {}
        context = SimpleNamespace(application=app)
        with (
            patch("bot.telegram_handlers.is_authorized", return_value=True),
            patch("bot.telegram_handlers.detect_restart_method", return_value=RestartMethod.EXEC),
            patch("bot.telegram_handlers.restart_method_hint", return_value="reinicio del proceso"),
            patch("bot.telegram_handlers.asyncio.create_task") as create_task,
        ):
            asyncio.run(reiniciar_command(update, context))
        update.message.reply_text.assert_awaited_once()
        create_task.assert_called_once()


class RestartBotTests(unittest.IsolatedAsyncioTestCase):
    async def test_exec_restart_after_graceful_shutdown(self) -> None:
        app = MagicMock()
        app.bot_data = {"scheduler": MagicMock()}
        app.updater.running = True
        app.running = True
        app.updater.stop = AsyncMock()
        app.stop = AsyncMock()

        with (
            patch("bot.restart_service.detect_restart_method", return_value=RestartMethod.EXEC),
            patch("bot.restart_service._restart_via_exec") as exec_restart,
        ):
            await restart_bot(app, delay_seconds=0)

        app.updater.stop.assert_awaited_once()
        app.stop.assert_awaited_once()
        exec_restart.assert_called_once()


if __name__ == "__main__":
    unittest.main()
