#!/usr/bin/env bash
set -euo pipefail

echo "=== SafeClaw Install ==="

# Check Python 3.11+
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 not found. Install Python 3.11+ first."
    exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
    echo "Error: Python 3.11+ required (found $PY_VERSION)"
    exit 1
fi

echo "Found Python $PY_VERSION"

# Install safeclaw package
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Installing safeclaw..."
pip install -e "$PROJECT_DIR"

# Generate default config
echo "Setting up default config..."
python3 "$SCRIPT_DIR/setup-config.py"

echo ""
echo "=== SafeClaw installed successfully ==="
echo ""
echo "Next steps:"
echo "  safeclaw serve          # Start the governance service"
echo "  safeclaw init           # Re-generate config"
echo "  safeclaw --help         # See all commands"
