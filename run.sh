#!/usr/bin/env bash
# OpenStick Linux Installer launcher for Linux
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
    echo ""
    echo "========================================================"
    echo "[!] Python 3 was not detected on your system."
    echo ""
    echo "Please install Python 3 and venv:"
    echo "  Debian/Ubuntu: sudo apt install python3 python3-venv"
    echo "  Fedora:        sudo dnf install python3"
    echo "  Arch Linux:    sudo pacman -S python"
    echo "========================================================"
    echo ""
    if [ -t 0 ]; then
        read -n 1 -s -r -p "Press any key to close this window..."
        echo ""
    fi
    exit 1
fi

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
