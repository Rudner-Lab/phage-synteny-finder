#!/usr/bin/env python3
"""
report_orpham_synteny.py — entry-point shim.

The implementation lives in the orpham_report/ package.
Run this script or import orpham_report.cli directly.

Usage
-----
  .venv/bin/python report_orpham_synteny.py --cluster F1
  .venv/bin/python report_orpham_synteny.py --cluster "F*"
  .venv/bin/python report_orpham_synteny.py --cluster F1 F2 K1
  .venv/bin/python report_orpham_synteny.py --cluster all
  .venv/bin/python report_orpham_synteny.py --help
"""
from orpham_report.cli import main

if __name__ == "__main__":
    main()
