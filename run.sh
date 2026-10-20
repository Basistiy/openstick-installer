#!/usr/bin/env bash
# OpenStick Linux Flasher launcher for Linux
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# If stdout is not an interactive terminal (e.g. launched via GUI file manager double-click),
# re-launch inside an available graphical terminal emulator.
if [ ! -t 0 ] || [ ! -t 1 ]; then
    for term in x-terminal-emulator gnome-terminal konsole xfce4-terminal mate-terminal alacritty kitty xterm; do
        if command -v "$term" >/dev/null 2>&1; then
            exec "$term" -e "$SCRIPT_DIR/run.sh" "$@"
        fi
    done
fi

python3 "$SCRIPT_DIR/main.py" "$@"

if [ -t 0 ]; then
    echo ""
    read -n 1 -s -r -p "Press any key to close this window..."
    echo ""
fi
