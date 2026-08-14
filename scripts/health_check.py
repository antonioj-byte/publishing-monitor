#!/usr/bin/env python3
"""Run health checks on bot configuration and core pipeline."""

import socket
import sys
from pathlib import Path

socket.setdefaulttimeout(15)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import feedparser

from ai.classify import active_model, active_provider, verify_classify_api
from bot.config import settings, PROJECT_ROOT
from db.connection import get_connection, init_schema
from reports.generator import build_report, split_message


def check(name: str, ok: bool, detail: str = "") -> bool:
    mark = "OK" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def main() -> None:
    init_schema()
    results: list[bool] = []

    results.append(check(".env existe", (PROJECT_ROOT / ".env").exists()))
    results.append(check("TELEGRAM_BOT_TOKEN", bool(settings.telegram_bot_token.strip())))
    results.append(check("TELEGRAM_CHAT_ID", bool(settings.telegram_chat_id.strip())))
    provider = active_provider()
    results.append(check("CLASSIFY_PROVIDER", provider in ("gemini", "anthropic"), provider))

    if settings.has_classify_api():
        try:
            verify_classify_api()
            model = active_model()
            results.append(check(f"API clasificación ({provider})", True, model))
        except Exception as exc:
            results.append(check(f"API clasificación ({provider})", False, str(exc)[:80]))
    else:
        key_name = "GOOGLE_API_KEY" if provider == "gemini" else "ANTHROPIC_API_KEY"
        results.append(check(f"{key_name} presente", False, "clasificación offline"))

    if settings.telegram_bot_token.strip():
        try:
            import json, urllib.request
            url = f"https://api.telegram.org/bot{settings.telegram_bot_token.strip()}/getMe"
            with urllib.request.urlopen(url, timeout=10) as r:
                data = json.loads(r.read())
            results.append(check("Telegram bot token", data.get("ok", False),
                                 f"@{data.get('result', {}).get('username', '?')}"))
        except Exception as exc:
            results.append(check("Telegram bot token", False, str(exc)[:60]))

    with get_connection() as c:
        medios = c.execute("SELECT COUNT(*) FROM medios WHERE activo=1").fetchone()[0]
        arts = c.execute("SELECT COUNT(*) FROM articulos").fetchone()[0]
        proc = c.execute("SELECT COUNT(*) FROM articulos WHERE procesado=1").fetchone()[0]
    results.append(check("Base de datos", medios >= 90, f"{medios} medios, {arts} artículos, {proc} procesados"))

    feed = feedparser.parse("https://www.ft.com/books?format=rss", agent="EditorialBot/1.0")
    results.append(check("Feed FT Books", len(feed.entries) > 0, f"{len(feed.entries)} entradas"))

    report = build_report("informe")
    chunks = split_message(report.text)
    results.append(
        check(
            "Generador informe",
            len(chunks) <= 10,
            f"{len(report.article_ids)} artículos, {len(chunks)} mensajes Telegram"
            + (f" (total en BD: {report.total_matched})" if report.truncated else ""),
        )
    )

    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} comprobaciones OK")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
