#!/usr/bin/env python3
"""Print a sample report to stdout."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.connection import init_schema
from reports.generator import build_report

if __name__ == "__main__":
    init_schema()
    for mode in ("informe", "informe_hoy"):
        report = build_report(mode=mode)
        print(f"\n{'='*60}\nMODE: {mode}\n{'='*60}\n")
        print(report.text)
