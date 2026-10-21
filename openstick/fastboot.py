"""Fastboot communication and management for OpenStick devices."""

import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class FastbootDevice:
    serial: str
    state: str = "fastboot"


def is_fastboot_available() -> bool:
    """Check if fastboot binary is installed and present in PATH."""
    return shutil.which("fastboot") is not None


def get_fastboot_devices() -> List[FastbootDevice]:
    """Execute 'fastboot devices' and parse connected devices."""
    if not is_fastboot_available():
        return []

    try:
        res = subprocess.run(
            ["fastboot", "devices"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return []

    devices = []
    for line in res.stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            devices.append(FastbootDevice(serial=parts[0], state=parts[1]))
        elif len(parts) == 1:
            devices.append(FastbootDevice(serial=parts[0], state="fastboot"))
    return devices


def wait_for_device(timeout: int = 5) -> Optional[FastbootDevice]:
    """Poll for a connected fastboot device within timeout seconds."""
    start = time.time()
    while time.time() - start < timeout:
        devices = get_fastboot_devices()
        if devices:
            return devices[0]
        time.sleep(1)
    return None


def reboot_to_edl(serial: Optional[str] = None, dry_run: bool = False) -> bool:
    """
    Reboot connected device from fastboot into Qualcomm Emergency Download (EDL / 9008) mode.
    Tries in priority order:
      1. 'fastboot oem reboot-edl' (verified standard on MSM8916 OpenStick aboot bootloader)
      2. 'fastboot oem edl' (fallback)
      3. 'fastboot reboot-edl' (fallback on specific platform tools builds)
    """
    if dry_run:
        print("[DRY-RUN] Simulating 'fastboot oem reboot-edl'...")
        return True

    cmd_prefix = ["fastboot"]
    if serial:
        cmd_prefix.extend(["-s", serial])

    commands = [
        ["oem", "reboot-edl"],
        ["oem", "edl"],
        ["reboot-edl"],
    ]

    for cmd_args in commands:
        cmd = cmd_prefix + cmd_args
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            combined = (res.stdout + "\n" + res.stderr).lower()
            if "unknown command" in combined or "failed" in combined:
                continue
            if res.returncode == 0 or "okay" in combined:
                return True
        except subprocess.SubprocessError:
            continue

    return False


def reboot_bootloader(serial: Optional[str] = None, dry_run: bool = False) -> bool:
    """Reboot device back into bootloader / fastboot."""
    if dry_run:
        print("[DRY-RUN] Simulating 'fastboot reboot bootloader'...")
        return True

    cmd = ["fastboot"]
    if serial:
        cmd.extend(["-s", serial])
    cmd.extend(["reboot", "bootloader"])

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return res.returncode == 0
    except subprocess.SubprocessError:
        return False
