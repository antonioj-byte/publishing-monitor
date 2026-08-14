#!/usr/bin/env python3
"""Sync media tiers in DB from medios_tiers.py (single source of truth)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.connection import get_connection, init_schema
from medios_tiers import TIER1_ALL, get_tier, tier_label


def main() -> None:
    init_schema()

    changes: list[tuple[str, int, int]] = []
    with get_connection() as conn:
        rows = conn.execute("SELECT nombre, tier FROM medios ORDER BY nombre").fetchall()
        for row in rows:
            canonical = get_tier(row["nombre"])
            if row["tier"] != canonical:
                changes.append((row["nombre"], row["tier"], canonical))
                conn.execute(
                    "UPDATE medios SET tier = ? WHERE nombre = ?",
                    (canonical, row["nombre"]),
                )
        conn.commit()

    print(f"\nTier 1 canon ({len(TIER1_ALL)} medios):")
    for name in sorted(TIER1_ALL):
        print(f"  · {name}")

    if changes:
        print(f"\nTiers corregidos en BD ({len(changes)}):")
        for name, old, new in changes:
            print(f"  {name}: {tier_label(old)} → {tier_label(new)}")
    else:
        print("\nBD ya alineada con medios_tiers.py.")

    t1 = sum(1 for r in rows if get_tier(r["nombre"]) == 1)
    print(f"\nTotal Tier 1 en BD: {t1}")


if __name__ == "__main__":
    main()
