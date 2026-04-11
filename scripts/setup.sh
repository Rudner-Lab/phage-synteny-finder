#!/usr/bin/env bash
# setup.sh — first-time repository setup for Phage Synteny Tools.
#
# What this does:
#   1. Checks the Python version (3.10+ required).
#   2. Creates a Python virtual environment (.venv) if one doesn't exist.
#   3. Installs Python dependencies from requirements.txt.
#   4. Installs the pre-commit test hook into .git/hooks/.
#   5. Runs the unit test suite to verify the installation.
#   6. Optionally runs the Phamerator data scrape to populate phamerator.sqlite,
#      followed by the smoke tests to verify the result.
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
# 1. Python version check
# ---------------------------------------------------------------------------
PYTHON=python3
if ! command -v "$PYTHON" &>/dev/null; then
    echo "ERROR: python3 not found. Install Python 3.10 or newer and try again."
    exit 1
fi

PY_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$("$PYTHON" -c "import sys; print(sys.version_info.major)")
PY_MINOR=$("$PYTHON" -c "import sys; print(sys.version_info.minor)")

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    echo "ERROR: Python 3.10+ is required, but you have Python $PY_VERSION."
    echo "Please install a newer Python and try again."
    exit 1
fi
echo "Python $PY_VERSION — OK"

# ---------------------------------------------------------------------------
# 2. Virtual environment
# ---------------------------------------------------------------------------
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    "$PYTHON" -m venv .venv
    echo "  Done."
else
    echo "Virtual environment already exists — skipping creation."
fi

# ---------------------------------------------------------------------------
# 3. Dependencies
# ---------------------------------------------------------------------------
echo "Installing dependencies..."
.venv/bin/pip install -r requirements.txt -q
echo "  Done."
echo

# ---------------------------------------------------------------------------
# 4. Pre-commit hook
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
# 5. Unit tests
# ---------------------------------------------------------------------------
echo "Running unit tests..."
if .venv/bin/python -m pytest tests/ -q --ignore=tests/test_smoke.py; then
    echo "  All unit tests passed."
else
    echo ""
    echo "ERROR: Unit tests failed. The installation may be incomplete or broken."
    echo "Please review the output above before continuing."
    exit 1
fi
echo

# ---------------------------------------------------------------------------
# 6. Data download (interactive)
# ---------------------------------------------------------------------------
if [ -f "phamerator.sqlite" ]; then
    echo "Database phamerator.sqlite already exists — skipping scrape."
    echo
    echo "Running smoke tests against existing database..."
    .venv/bin/python -m pytest tests/test_smoke.py -q && echo "  Smoke tests passed." || echo "  WARNING: Smoke tests failed — database may be incomplete."
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
            echo
            echo "Running smoke tests to verify the database..."
            .venv/bin/python -m pytest tests/test_smoke.py -q && echo "  Smoke tests passed." || echo "  WARNING: Smoke tests failed — some phages may not have been scraped correctly."
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
