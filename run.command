#!/usr/bin/env bash
# macOS double-clickable Terminal launcher for OpenStick Installer

# Resolve actual script directory (Terminal opens .command files in $HOME by default)
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if ! command -v python3 >/dev/null 2>&1; then
    echo ""
    echo "========================================================"
    echo "[!] Python 3 was not detected on your Mac."
    echo ""
    echo "Please install Python 3 from:"
    echo "  https://www.python.org/downloads/"
    echo "or via Homebrew: 'brew install python'"
    echo "========================================================"
    echo ""
    read -n 1 -s -r -p "Press any key to close this window..."
    echo ""
    exit 1
fi

# Launch installer with python3
python3 main.py "$@"

# Keep terminal window open on completion
echo ""
read -n 1 -s -r -p "Press any key to close this window..."
echo ""
