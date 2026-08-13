#!/usr/bin/env python3
"""Initialize SQLite schema."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.connection import init_schema


def main() -> None:
    init_schema()
    print("Database schema initialized.")


if __name__ == "__main__":
    main()
