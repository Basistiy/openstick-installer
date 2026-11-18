"""OpenStick Installer package."""

import os
import sys
from pathlib import Path

__version__ = "0.0.6"


def _init_windows_libusb():
    """Ensure bundled libusb-1.0 DLL is discoverable by PyUSB/ctypes on Windows."""
    if sys.platform == "win32":
        try:
            import libusb

            base = Path(libusb.__file__).resolve().parent
            arch = "x86_64" if sys.maxsize > 2**32 else "x86"
            dll_dir = base / "_platform" / "windows" / arch
            if dll_dir.is_dir():
                os.environ["PATH"] = str(dll_dir) + os.pathsep + os.environ.get("PATH", "")
                if hasattr(os, "add_dll_directory"):
                    try:
                        os.add_dll_directory(str(dll_dir))
                    except OSError:
                        pass
        except Exception:
            pass


_init_windows_libusb()
