#!/usr/bin/env bash
# macOS double-clickable Terminal launcher for OpenStick Flasher

# Resolve actual script directory (Terminal opens .command files in $HOME by default)
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Launch flasher with python3
python3 main.py "$@"

# Keep terminal window open on completion
echo ""
read -n 1 -s -r -p "Press any key to close this window..."
echo ""
