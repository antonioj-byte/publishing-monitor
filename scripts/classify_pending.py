#!/usr/bin/env python3
"""Classify all pending articles."""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.classify import classify_pending
from db.connection import init_schema

logging.basicConfig(level=logging.INFO)


def main() -> None:
    init_schema()
    total_classified = 0
    while True:
        stats = classify_pending(limit=20)
        total_classified += stats["classified"]
        print(stats)
        if stats["remaining"] == 0 or stats["classified"] == 0:
            break
    print(f"Total classified: {total_classified}")


if __name__ == "__main__":
    main()
