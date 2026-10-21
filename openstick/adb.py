"""ADB communication and management for OpenStick devices."""

import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class AdbDevice:
    serial: str
    state: str  # "device", "unauthorized", "offline", "recovery", etc.
    model: Optional[str] = None
    product: Optional[str] = None

    @property
    def is_ready(self) -> bool:
        return self.state == "device"


def is_adb_available() -> bool:
    """Check if adb binary is installed and present in PATH."""
    return shutil.which("adb") is not None


def get_adb_devices() -> List[AdbDevice]:
    """Execute 'adb devices -l' and parse all connected devices."""
    if not is_adb_available():
        return []

    try:
        res = subprocess.run(
            ["adb", "devices", "-l"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return []

    devices = []
    lines = res.stdout.strip().splitlines()
    for line in lines[1:]:  # skip 'List of devices attached' header
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            serial = parts[0]
            state = parts[1]
            model = None
            product = None
            for p in parts[2:]:
                if p.startswith("model:"):
                    model = p.split("model:", 1)[1]
                elif p.startswith("product:"):
                    product = p.split("product:", 1)[1]
            devices.append(AdbDevice(serial=serial, state=state, model=model, product=product))
    return devices


def prepare_root(serial: Optional[str] = None) -> bool:
    """Attempt to enable ADB root mode on stock MSM8916 firmware."""
    cmd_prefix = ["adb"]
    if serial:
        cmd_prefix.extend(["-s", serial])

    # First attempt: standard adb root
    try:
        subprocess.run(cmd_prefix + ["root"], capture_output=True, text=True, timeout=5)
    except Exception:
        pass

    # Second attempt: setprop service.adb.root 1 and restart adbd
    try:
        subprocess.run(
            cmd_prefix + ["shell", "setprop service.adb.root 1"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        subprocess.run(
            cmd_prefix + ["shell", "busybox killall adbd || killall adbd"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        time.sleep(2)
        return True
    except Exception:
        return False


def reboot_to_edl(serial: Optional[str] = None, dry_run: bool = False) -> bool:
    """Reboot connected device into Emergency Download (EDL / 9008) mode."""
    if dry_run:
        print("[DRY-RUN] Simulating 'adb reboot edl'...")
        return True

    cmd = ["adb"]
    if serial:
        cmd.extend(["-s", serial])
    cmd.extend(["reboot", "edl"])

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return res.returncode == 0
    except subprocess.SubprocessError as e:
        print(f"[-] ADB reboot command failed: {e}")
        return False


def reboot_to_bootloader(serial: Optional[str] = None, dry_run: bool = False) -> bool:
    """Reboot connected device into Bootloader / Fastboot mode."""
    if dry_run:
        print("[DRY-RUN] Simulating 'adb reboot bootloader'...")
        return True

    cmd = ["adb"]
    if serial:
        cmd.extend(["-s", serial])
    cmd.extend(["reboot", "bootloader"])

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return res.returncode == 0
    except subprocess.SubprocessError as e:
        print(f"[-] ADB reboot bootloader command failed: {e}")
        return False


def wait_for_device(timeout: int = 20) -> Optional[AdbDevice]:
    """Poll for a connected and authorized ADB device within timeout seconds."""
    start = time.time()
    while time.time() - start < timeout:
        devices = get_adb_devices()
        ready_devices = [d for d in devices if d.is_ready]
        if ready_devices:
            return ready_devices[0]
        time.sleep(1)
    return None
