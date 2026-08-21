"""Track LLM API usage and estimate costs for /gasto."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bot.config import settings
from db.connection import get_connection

logger = logging.getLogger(__name__)

# USD per 1M tokens (orientativo — revisar tarifas del proveedor).
_PRICING_PER_MILLION: dict[tuple[str, str], tuple[float, float]] = {
    ("gemini", "gemini-2.5-flash"): (0.30, 2.50),
    ("gemini", "gemini-3.1-flash-lite"): (0.10, 0.40),
    ("gemini", "default"): (0.30, 2.50),
    ("anthropic", "claude-haiku-4-5"): (1.00, 5.00),
    ("anthropic", "claude-sonnet-5"): (3.00, 15.00),
    ("anthropic", "default"): (1.00, 5.00),
}

# Fallback when no token metadata (clasificación típica).
_CLASSIFY_AVG_USD = {
    "gemini": 0.00025,
    "anthropic": 0.0015,
}
_VOICE_AVG_USD = 0.0004


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def estimate_cost_usd(
    *,
    provider: str,
    model: str | None,
    input_tokens: int,
    output_tokens: int,
) -> float:
    key = (provider, model or "default")
    in_rate, out_rate = _PRICING_PER_MILLION.get(
        key,
        _PRICING_PER_MILLION.get((provider, "default"), (0.50, 2.00)),
    )
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000


def _safe_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def _extract_gemini_tokens(response: object) -> tuple[int, int]:
    meta = getattr(response, "usage_metadata", None)
    if not meta:
        return 0, 0
    inp = _safe_int(getattr(meta, "prompt_token_count", 0))
    out = _safe_int(getattr(meta, "candidates_token_count", 0))
    return inp, out


def _extract_anthropic_tokens(response: object) -> tuple[int, int]:
    usage = getattr(response, "usage", None)
    if not usage:
        return 0, 0
    return _safe_int(getattr(usage, "input_tokens", 0)), _safe_int(
        getattr(usage, "output_tokens", 0)
    )


def record_api_usage(
    *,
    operation: str,
    provider: str,
    model: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    estimated_usd: float | None = None,
) -> None:
    """Persist one API call; failures are logged and ignored."""
    if estimated_usd is None:
        estimated_usd = estimate_cost_usd(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
    try:
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO api_usage_events (
                    operation, provider, model, input_tokens, output_tokens, estimated_usd
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (operation, provider, model, input_tokens, output_tokens, estimated_usd),
            )
            conn.commit()
    except Exception:
        logger.exception("Failed recording API usage (%s/%s)", operation, provider)


def record_llm_call(
    *,
    operation: str,
    provider: str,
    model: str,
    response: object | None = None,
    prompt_text: str = "",
    output_text: str = "",
) -> None:
    input_tokens = output_tokens = 0
    if provider == "gemini" and response is not None:
        input_tokens, output_tokens = _extract_gemini_tokens(response)
    elif provider == "anthropic" and response is not None:
        input_tokens, output_tokens = _extract_anthropic_tokens(response)

    if input_tokens == 0 and prompt_text:
        input_tokens = estimate_tokens(prompt_text)
    if output_tokens == 0 and output_text:
        output_tokens = estimate_tokens(output_text)

    record_api_usage(
        operation=operation,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _since_iso(days: int) -> str:
    since = datetime.now(ZoneInfo(settings.timezone)) - timedelta(days=days)
    return since.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M:%S")


def _format_usd(amount: float) -> str:
    if amount < 0.01:
        return f"${amount:.4f}"
    if amount < 1:
        return f"${amount:.3f}"
    return f"${amount:.2f}"


def _query_period_stats(since_iso: str | None) -> dict[str, float | int]:
    clause = ""
    params: tuple[object, ...] = ()
    if since_iso:
        clause = "WHERE created_at >= ?"
        params = (since_iso,)

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT operation, provider, COUNT(*) AS calls,
                   COALESCE(SUM(input_tokens), 0) AS inp,
                   COALESCE(SUM(output_tokens), 0) AS outp,
                   COALESCE(SUM(estimated_usd), 0) AS usd
            FROM api_usage_events
            {clause}
            GROUP BY operation, provider
            ORDER BY usd DESC
            """,
            params,
        ).fetchall()
        total = conn.execute(
            f"""
            SELECT COUNT(*), COALESCE(SUM(estimated_usd), 0),
                   COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0)
            FROM api_usage_events
            {clause}
            """,
            params,
        ).fetchone()

    by_op: dict[str, dict[str, float | int]] = {}
    for row in rows:
        op = row["operation"]
        bucket = by_op.setdefault(
            op,
            {"calls": 0, "usd": 0.0, "inp": 0, "outp": 0},
        )
        bucket["calls"] = int(bucket["calls"]) + int(row["calls"])
        bucket["usd"] = float(bucket["usd"]) + float(row["usd"])
        bucket["inp"] = int(bucket["inp"]) + int(row["inp"])
        bucket["outp"] = int(bucket["outp"]) + int(row["outp"])

    return {
        "calls": int(total[0]),
        "usd": float(total[1]),
        "inp": int(total[2]),
        "outp": int(total[3]),
        "by_operation": by_op,
    }


def _historical_classify_estimate(provider: str) -> tuple[int, float]:
    """Articles classified before usage tracking (approximate)."""
    with get_connection() as conn:
        total_classified = conn.execute(
            "SELECT COUNT(*) FROM articulos WHERE procesado = 1"
        ).fetchone()[0]
        tracked = conn.execute(
            "SELECT COUNT(*) FROM api_usage_events WHERE operation = 'classify'"
        ).fetchone()[0]
    untracked = max(0, int(total_classified) - int(tracked))
    avg = _CLASSIFY_AVG_USD.get(provider, 0.0005)
    return untracked, untracked * avg


_OPERATION_LABELS = {
    "classify": "Clasificación",
    "voice": "Voz (transcripción)",
    "verify": "Verificación API",
}


def format_gasto_text(*, days: int = 30) -> str:
    from ai.classify import active_model, active_provider
    from db.connection import init_schema

    init_schema()
    provider = active_provider()
    model = active_model()

    stats_7 = _query_period_stats(_since_iso(7))
    stats_period = _query_period_stats(_since_iso(days))
    stats_all = _query_period_stats(None)

    untracked_n, untracked_usd = _historical_classify_estimate(provider)

    lines = [
        "💰 Gasto API estimado del bot",
        "",
        f"Proveedor activo: {provider} ({model})",
        f"Ventana principal: últimos {days} días",
        "",
    ]

    def _append_period(title: str, stats: dict) -> None:
        lines.append(title)
        if stats["calls"] == 0:
            lines.append("  (sin llamadas registradas aún)")
        else:
            for op, bucket in stats["by_operation"].items():
                label = _OPERATION_LABELS.get(op, op)
                lines.append(
                    f"  · {label}: {bucket['calls']} llamadas · "
                    f"{_format_usd(float(bucket['usd']))}"
                )
            lines.append(
                f"  Total: {stats['calls']} llamadas · "
                f"{_format_usd(float(stats['usd']))} · "
                f"{stats['inp']:,} tok in / {stats['outp']:,} tok out"
            )
        lines.append("")

    _append_period("Últimos 7 días", stats_7)
    _append_period(f"Últimos {days} días", stats_period)
    _append_period("Todo el histórico medido", stats_all)

    if untracked_n > 0:
        lines.extend(
            [
                "Estimado previo a medición:",
                f"  · {untracked_n} clasificaciones sin registro × "
                f"~{_format_usd(_CLASSIFY_AVG_USD.get(provider, 0.0005))} ≈ "
                f"{_format_usd(untracked_usd)}",
                "",
            ]
        )

    billing_hint = (
        "https://aistudio.google.com/apikey"
        if provider == "gemini"
        else "https://console.anthropic.com/settings/billing"
    )
    lines.extend(
        [
            "ℹ️ Cifras orientativas según tarifas publicadas; "
            "pueden diferir de la factura real.",
            f"Facturación: {billing_hint}",
            "",
            "Uso: /gasto · /gasto 7 · /gasto 90",
        ]
    )
    return "\n".join(lines)


def init_usage_schema() -> None:
    """Ensure api_usage_events exists (also called from db migration)."""
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS api_usage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                operation TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                estimated_usd REAL NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_api_usage_created
            ON api_usage_events (created_at DESC)
            """
        )
        conn.commit()
