#!/usr/bin/env python3
"""Print a sample report to stdout."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.report_parser import parse_command_args
from db.connection import init_schema
from db.models import ReportFilter
from reports.pipeline import build_editorial_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview editorial report")
    parser.add_argument("args", nargs="*", help="e.g. 7 alemania")
    args = parser.parse_args()

    init_schema()

    if args.args:
        parsed = parse_command_args(args.args)
        if not parsed:
            print("Provide days and country, e.g.: python3 scripts/print_report.py 7 alemania")
            sys.exit(1)
        report_filter = ReportFilter(
            days=parsed.days,
            pais=parsed.pais,
            region=parsed.region,
            location_label=parsed.location_label,
        )
        report = build_editorial_report(mode="informe_pais", report_filter=report_filter)
        print(f"\n{'='*60}\nFILTER: {parsed.location_label}, {parsed.days} días\n{'='*60}\n")
        print(report.text)
        return

    for mode in ("informe", "informe_hoy"):
        report = build_editorial_report(mode=mode)
        print(f"\n{'='*60}\nMODE: {mode}\n{'='*60}\n")
        print(report.text)


if __name__ == "__main__":
    main()
