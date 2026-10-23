"""ADB communication and management for OpenStick devices."""

import re
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


def validate_imei(imei: Optional[str]) -> bool:
    """
    Validate a 14 or 15-digit cellular IMEI string.
    Enforces numeric format and Luhn checksum for 15-digit IMEIs.
    """
    if not imei or not isinstance(imei, str):
        return False
    imei = imei.strip()
    if not (imei.isdigit() and len(imei) in (14, 15)):
        return False
    # Reject dummy strings with uniform digits (e.g. 000000000000000, 111111111111111)
    if len(set(imei)) <= 1:
        return False

    if len(imei) == 15:
        total = 0
        for i, ch in enumerate(reversed(imei)):
            n = int(ch)
            if i % 2 == 1:
                n *= 2
                if n > 9:
                    n -= 9
            total += n
        return total % 10 == 0

    return True  # 14-digit IMEI (IMEI without Luhn check digit)


def get_device_imei(serial: Optional[str] = None, dry_run: bool = False) -> Optional[str]:
    """
    Query modem IMEI from connected Android device via ADB.
    Checks:
      1. Android system properties (persist.radio.imei, gsm.baseband.imei, ro.ril.oem.imei, etc.)
      2. Android telephony service (dumpsys iphonesubinfo)
      3. Service call iphonesubinfo 1
      4. Direct modem AT command (AT+CGSN on /dev/smd11 or /dev/smd0)
    """
    if dry_run:
        return "860123456789014"

    cmd_prefix = ["adb"]
    if serial:
        cmd_prefix.extend(["-s", serial])

    # 1. Check Android system properties
    props_to_check = [
        "persist.radio.imei",
        "persist.radio.imei1",
        "gsm.baseband.imei",
        "ro.ril.oem.imei",
        "ril.imei",
    ]
    for prop in props_to_check:
        try:
            res = subprocess.run(
                cmd_prefix + ["shell", f"getprop {prop}"],
                capture_output=True,
                text=True,
                timeout=4,
            )
            candidate = res.stdout.strip()
            if validate_imei(candidate):
                return candidate
        except Exception:
            pass

    # 2. Check dumpsys iphonesubinfo
    try:
        res = subprocess.run(
            cmd_prefix + ["shell", "dumpsys iphonesubinfo"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0 and res.stdout:
            labeled = re.findall(r"(?:Device ID|IMEI)\s*(?:=|:)\s*([0-9]{14,15})", res.stdout, re.IGNORECASE)
            for cand in labeled:
                if validate_imei(cand):
                    return cand
            all_digits = re.findall(r"\b([0-9]{14,15})\b", res.stdout)
            for cand in all_digits:
                if validate_imei(cand):
                    return cand
    except Exception:
        pass

    # 3. Check service call iphonesubinfo 1
    try:
        res = subprocess.run(
            cmd_prefix + ["shell", "service call iphonesubinfo 1"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0 and res.stdout:
            quoted = re.findall(r"'([^']+)'", res.stdout)
            if quoted:
                clean_str = "".join(quoted).replace(".", "").replace("\x00", "").strip()
                m = re.search(r"\b([0-9]{14,15})\b", clean_str)
                if m and validate_imei(m.group(1)):
                    return m.group(1)
            all_digits = re.findall(r"\b([0-9]{14,15})\b", res.stdout)
            for cand in all_digits:
                if validate_imei(cand):
                    return cand
    except Exception:
        pass

    # 4. Check direct modem AT command on Qualcomm smd ports
    for port in ["/dev/smd11", "/dev/smd0", "/dev/smd7"]:
        try:
            check_port = subprocess.run(
                cmd_prefix + ["shell", f"[ -e {port} ] && echo yes || echo no"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if "yes" not in check_port.stdout.lower():
                continue

            at_cmd = f"echo -e 'AT+CGSN\\r' > {port} 2>/dev/null && timeout 1 cat {port} 2>/dev/null || true"
            res = subprocess.run(
                cmd_prefix + ["shell", at_cmd],
                capture_output=True,
                text=True,
                timeout=3,
            )
            candidates = re.findall(r"\b([0-9]{14,15})\b", res.stdout)
            for cand in candidates:
                if validate_imei(cand):
                    return cand
        except Exception:
            pass

    return None
