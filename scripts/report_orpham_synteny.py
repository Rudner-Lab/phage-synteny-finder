#!/usr/bin/env python3
"""
report_orpham_synteny.py — entry-point shim.

The implementation lives in the orpham_report/ package.
Run this script from the repo root with the project's virtual environment.

Usage
-----
  .venv/bin/python scripts/report_orpham_synteny.py --cluster F1
  .venv/bin/python scripts/report_orpham_synteny.py --cluster "F*"
  .venv/bin/python scripts/report_orpham_synteny.py --cluster F1 F2 K1
  .venv/bin/python scripts/report_orpham_synteny.py --cluster all
  .venv/bin/python scripts/report_orpham_synteny.py --phage LordVader
  .venv/bin/python scripts/report_orpham_synteny.py --help
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orpham_report.cli import main

if __name__ == "__main__":
    main()
