#!/usr/bin/env bash
# setup.sh — first-time repository setup for Phage Synteny Tools.
#
# What this does:
#   1. Creates a Python virtual environment (.venv) if one doesn't exist.
#   2. Installs Python dependencies from requirements.txt.
#   3. Installs the pre-commit test hook into .git/hooks/.
#   4. Optionally runs the Phamerator data scrape to populate phamerator.sqlite.
#
# Usage:
#   bash scripts/setup.sh

set -euo pipefail

# Always run from the repo root regardless of where the script is called from.
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== Phage Synteny Tools — Setup ==="
echo

# ---------------------------------------------------------------------------
# 1. Virtual environment
# ---------------------------------------------------------------------------
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    echo "  Done."
else
    echo "Virtual environment already exists — skipping creation."
fi

# ---------------------------------------------------------------------------
# 2. Dependencies
# ---------------------------------------------------------------------------
echo "Installing dependencies..."
.venv/bin/pip install -r requirements.txt -q
echo "  Done."
echo

# ---------------------------------------------------------------------------
# 3. Pre-commit hook
# ---------------------------------------------------------------------------
HOOK_SRC="scripts/hooks/pre-commit"
HOOK_DST=".git/hooks/pre-commit"

if [ ! -f "$HOOK_SRC" ]; then
    echo "WARNING: Hook source not found at $HOOK_SRC — skipping hook installation."
elif [ -f "$HOOK_DST" ] && diff -q "$HOOK_SRC" "$HOOK_DST" > /dev/null 2>&1; then
    echo "Pre-commit hook is already up to date."
else
    cp "$HOOK_SRC" "$HOOK_DST"
    chmod +x "$HOOK_DST"
    echo "Pre-commit hook installed at $HOOK_DST."
    echo "  Tests will run automatically before each commit."
    echo "  To skip: SKIP_TESTS=true git commit -m \"...\""
fi
echo

# ---------------------------------------------------------------------------
# 4. Data download (interactive)
# ---------------------------------------------------------------------------
if [ -f "phamerator.sqlite" ]; then
    echo "Database phamerator.sqlite already exists — skipping scrape."
else
    echo "No database found (phamerator.sqlite)."
    echo "The scrape downloads all phage and gene data from the Phamerator API."
    echo "It requires Phamerator credentials and takes several minutes."
    echo
    read -r -p "Download phage data now? [y/N] " answer
    echo
    case "$answer" in
        [Yy]*)
            echo "Starting scrape. You will be prompted for credentials if not set in .env."
            .venv/bin/python scrape_phamerator.py
            ;;
        *)
            echo "Skipped. Run the following when ready:"
            echo "  .venv/bin/python scrape_phamerator.py"
            ;;
    esac
fi

echo
echo "=== Setup complete ==="
echo
echo "Quick start:"
echo "  .venv/bin/python scripts/report_orpham_synteny.py --cluster F1"
echo "  .venv/bin/python scripts/generate_cluster_reports.py"
echo "  .venv/bin/python -m pytest tests/ -q"
