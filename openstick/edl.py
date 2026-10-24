"""Qualcomm EDL (Emergency Download / 9008 mode) and raw eMMC image engine."""

import os
import re
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

QUALCOMM_VID = 0x05C6
QUALCOMM_EDL_PID = 0x9008

DEFAULT_CALIBRATION_PARTITIONS = ["fsc", "fsg", "modemst1", "modemst2", "persist", "sec"]
ALL_CALIBRATION_PARTITIONS = ["fsc", "fsg", "modem", "modemst1", "modemst2", "persist", "sec"]
DEFAULT_SANITIZE_PARTITIONS = ["fsc", "fsg", "modemst1", "modemst2", "persist", "sec", "misc", "ssd"]


# ---------------------------------------------------------------------------
# EDL Hardware Detection
# ---------------------------------------------------------------------------

def detect_edl_via_pyusb() -> bool:
    """Detect Qualcomm 9008 device using pyusb."""
    try:
        import usb.core
        dev = usb.core.find(idVendor=QUALCOMM_VID, idProduct=QUALCOMM_EDL_PID)
        return dev is not None
    except Exception:
        return False


def detect_edl_via_serial() -> bool:
    """Detect Qualcomm 9008 port using pyserial."""
    try:
        import serial.tools.list_ports
        for port in serial.tools.list_ports.comports():
            vid = getattr(port, "vid", None)
            pid = getattr(port, "pid", None)
            desc = (getattr(port, "description", "") or "").lower()
            hwid = (getattr(port, "hwid", "") or "").lower()
            if vid == QUALCOMM_VID and pid == QUALCOMM_EDL_PID:
                return True
            if "9008" in desc or "qdloader" in desc or "05c6:9008" in hwid:
                return True
    except Exception:
        pass
    return False


def detect_edl_via_system_profiler() -> bool:
    """Detect Qualcomm 9008 device on macOS using system_profiler."""
    if sys.platform != "darwin":
        return False
    try:
        res = subprocess.run(
            ["system_profiler", "SPUSBDataType"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = res.stdout.lower()
        if "0x05c6" in output and "0x9008" in output:
            return True
        if "qdloader" in output or ("qualcomm" in output and "9008" in output):
            return True
    except Exception:
        pass
    return False


def detect_edl_via_lsusb() -> bool:
    """Detect Qualcomm 9008 device on Linux using lsusb."""
    if not shutil.which("lsusb"):
        return False
    try:
        res = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=5)
        output = res.stdout.lower()
        return "05c6:9008" in output or ("9008" in output and "qualcomm" in output)
    except Exception:
        return False


def is_edl_connected() -> bool:
    """Cross-platform detection for Qualcomm HS-USB QDLoader 9008 mode."""
    return (
        detect_edl_via_pyusb()
        or detect_edl_via_serial()
        or detect_edl_via_system_profiler()
        or detect_edl_via_lsusb()
    )


def wait_for_edl(timeout: int = 30, dry_run: bool = False) -> bool:
    """Poll for Qualcomm 9008 device until timeout seconds elapsed."""
    if dry_run:
        print("[DRY-RUN] Simulating EDL mode detection (Qualcomm 9008)...")
        time.sleep(1)
        return True

    print(f"[*] Waiting for Qualcomm EDL 9008 device (timeout: {timeout}s)...")
    start = time.time()
    while time.time() - start < timeout:
        if is_edl_connected():
            print("[+] Qualcomm 9008 EDL device detected!")
            return True
        time.sleep(1)
        print(".", end="", flush=True)
    print("\n[-] Timed out waiting for EDL device.")
    return False


# ---------------------------------------------------------------------------
# EDL Runner & Loaders
# ---------------------------------------------------------------------------

def find_edl_runner() -> Optional[List[str]]:
    """
    Find the command to execute bkerler/edl tool.
    Checks:
    1. 'edl' binary in PATH
    2. Current Python module 'python -m edl'
    3. Cloned/local './edl/edl.py'
    """
    # 1. System PATH
    if shutil.which("edl"):
        return ["edl"]

    # 2. Python module
    try:
        res = subprocess.run(
            [sys.executable, "-m", "edl", "--help"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if res.returncode == 0 or "Qualcomm" in res.stdout or "Qualcomm" in res.stderr:
            return [sys.executable, "-m", "edl"]
    except Exception:
        pass

    # 3. Local script in repo
    local_edl = Path(__file__).resolve().parent.parent / "edl" / "edl.py"
    if local_edl.exists():
        return [sys.executable, str(local_edl)]

    return None


def resolve_loader(device_loader: Optional[str] = None) -> Optional[Path]:
    """Find appropriate MSM8916 firehose programmer binary if available."""
    loaders_dir = Path(__file__).resolve().parent.parent / "loaders"
    if not loaders_dir.exists():
        return None

    if device_loader:
        candidate = loaders_dir / device_loader
        if candidate.exists():
            return candidate

    default_loader = loaders_dir / "prog_emmc_firehose_8916.mbn"
    if default_loader.exists():
        return default_loader

    return None


def run_edl_command(args: List[str], loader: Optional[Path] = None, dry_run: bool = False, timeout: int = 1800) -> bool:
    """Execute an arbitrary edl command with loader, eMMC memory flag, and PYTHONPATH configured."""
    if dry_run:
        print(f"[DRY-RUN] Simulating EDL command: edl {' '.join(args)}")
        return True

    edl_cmd = find_edl_runner()
    if not edl_cmd:
        print("[-] EDL tool (bkerler/edl) not found.", file=sys.stderr)
        return False

    cmd = list(edl_cmd) + list(args)
    storage_cmds = {
        "printgpt", "gpt", "r", "rl", "rf", "rs",
        "w", "wl", "wf", "ws", "e", "es", "ep",
        "footer", "getstorageinfo", "getactiveslot", "modules", "qfil",
    }
    if args and args[0] in storage_cmds and not any(a.startswith("--memory=") for a in cmd):
        cmd.append("--memory=eMMC")
    if loader and loader.exists() and not any(a.startswith("--loader=") for a in cmd):
        cmd.append(f"--loader={loader}")

    env = os.environ.copy()
    edl_dir = Path(__file__).resolve().parent.parent / "edl"
    if edl_dir.exists():
        env["PYTHONPATH"] = str(edl_dir) + os.pathsep + env.get("PYTHONPATH", "")

    import threading

    stop_event = threading.Event()
    drew_progress = [False]
    start_time = time.time()

    def _edl_spinner() -> None:
        if stop_event.wait(0.2):
            return
        frames = ["|", "/", "-", "\\"]
        idx = 0
        while not stop_event.is_set():
            elapsed = time.time() - start_time
            mins, secs = divmod(int(elapsed), 60)
            frame = frames[idx % len(frames)]
            idx += 1
            sys.stdout.write(f"\r      [{frame}] EDL operation in progress... {mins:02d}:{secs:02d} elapsed")
            sys.stdout.flush()
            drew_progress[0] = True
            stop_event.wait(0.2)

    worker = threading.Thread(target=_edl_spinner, daemon=True)
    worker.start()

    is_reset_cmd = bool(args and args[0] == "reset")
    cmd_timeout = 10 if is_reset_cmd else timeout

    try:
        res = subprocess.run(
            cmd,
            env=env,
            cwd=str(edl_dir) if edl_dir.exists() else None,
            capture_output=True,
            text=True,
            timeout=cmd_timeout,
        )
    except subprocess.TimeoutExpired:
        stop_event.set()
        worker.join()
        if drew_progress[0]:
            sys.stdout.write("\r" + " " * 70 + "\r")
            sys.stdout.flush()
        if is_reset_cmd and not is_edl_connected():
            return True
        print("[-] EDL command timed out.", file=sys.stderr)
        return False
    except Exception as e:
        stop_event.set()
        worker.join()
        if drew_progress[0]:
            sys.stdout.write("\r" + " " * 70 + "\r")
            sys.stdout.flush()
        if is_reset_cmd and not is_edl_connected():
            return True
        print(f"[-] EDL execution error: {e}", file=sys.stderr)
        return False

    stop_event.set()
    worker.join()
    if drew_progress[0]:
        sys.stdout.write("\r" + " " * 70 + "\r")
        sys.stdout.flush()

    if is_reset_cmd:
        if res.returncode == 0 or not is_edl_connected():
            return True

    combined_out = (res.stdout or "") + "\n" + (res.stderr or "")
    fatal_markers = [
        "Error: Couldn't detect partition",
        "Error writing ",
        "Error on writing ",
        "No suitable loader found",
        "Connection detected, quiting",
        "Error on sahara handshake",
    ]
    if res.returncode == 0 and not any(m in combined_out for m in fatal_markers):
        for line in (res.stdout or "").splitlines():
            stripped = line.strip()
            if stripped.startswith("Wrote ") or stripped.startswith("Saved "):
                print(f"      {stripped}")
        return True
    else:
        err_msg = res.stderr.strip() or res.stdout.strip()
        if (
            "NotImplementedError" in combined_out
            or "Operation not supported" in combined_out
            or "libusb_win32" in combined_out
        ):
            print("\n" + "=" * 70, file=sys.stderr)
            print("[!] WINDOWS USB DRIVER CONFLICT DETECTED (Zadig required)", file=sys.stderr)
            print("=" * 70, file=sys.stderr)
            print("PyUSB / libusb cannot communicate directly with the Qualcomm 9008 stick", file=sys.stderr)
            print("because Windows is using the default Qualcomm serial/COM driver.", file=sys.stderr)
            print("\nTo fix this in 1 minute:", file=sys.stderr)
            print("  1. Download Zadig: https://zadig.akeo.ie", file=sys.stderr)
            print("  2. Open Zadig (Run as Administrator)", file=sys.stderr)
            print("  3. In top menu, select 'Options' -> check 'List All Devices'", file=sys.stderr)
            print("  4. In the dropdown, select 'QUSB_BULK' or 'Qualcomm HS-USB QDLoader 9008'", file=sys.stderr)
            print("     (Verify USB ID: 05C6 9008)", file=sys.stderr)
            print("  5. In the target driver selector (right of arrow), select 'WinUSB' (or 'libusb-win32')", file=sys.stderr)
            print("  6. Click 'Replace Driver' (or 'Install Driver')", file=sys.stderr)
            print("  7. Unplug the stick, plug it back in, and rerun run.bat", file=sys.stderr)
            print("=" * 70 + "\n", file=sys.stderr)
        else:
            print(f"[-] EDL command failed: {err_msg}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Raw Image GPT Parsing, Sanitization & Injection
# ---------------------------------------------------------------------------

def parse_gpt_from_raw_image(image_path: Path) -> Dict[str, Dict]:
    """
    Parse standard GPT partition table from the beginning of a raw eMMC image.
    Returns mapping of partition_name -> partition_dict, plus '__metadata__'.
    """
    if not image_path.exists():
        raise FileNotFoundError(f"Raw image file not found: {image_path}")

    with open(image_path, "rb") as f:
        # Sector 0 is Protective MBR (512 bytes)
        # Sector 1 is Primary GPT Header at offset 512
        f.seek(512)
        gpt_header_raw = f.read(512)
        if len(gpt_header_raw) < 92:
            raise ValueError("File is too small to contain a valid GPT header.")

        signature = gpt_header_raw[0:8]
        if signature != b"EFI PART":
            raise ValueError(f"Invalid GPT signature: {signature!r} (expected b'EFI PART').")

        # Unpack GPT Header fields
        # Format: < 8s 4s I I 4x Q Q Q Q 16s Q I I (88 bytes)
        fields = struct.unpack("<8s4sII4xQQQQ16sQII", gpt_header_raw[:88])
        # fields:
        # 0: sig, 1: rev, 2: hdr_size, 3: crc, 4: curr_lba, 5: backup_lba,
        # 6: first_usable, 7: last_usable, 8: disk_guid, 9: part_entry_lba,
        # 10: num_part_entries, 11: part_entry_size
        current_lba = fields[4]
        backup_lba = fields[5]
        first_usable_lba = fields[6]
        last_usable_lba = fields[7]
        part_entry_lba = fields[9]
        num_part_entries = fields[10]
        part_entry_size = fields[11]

        partitions: Dict[str, Dict] = {
            "__metadata__": {
                "current_lba": current_lba,
                "backup_lba": backup_lba,
                "first_usable_lba": first_usable_lba,
                "last_usable_lba": last_usable_lba,
                "num_part_entries": num_part_entries,
                "part_entry_size": part_entry_size,
                "total_sectors": backup_lba + 1,
                "total_bytes": (backup_lba + 1) * 512,
            }
        }

        # Seek to Partition Entries Array (typically LBA 2 -> offset 1024)
        entry_offset = part_entry_lba * 512
        f.seek(entry_offset)
        entries_data = f.read(num_part_entries * part_entry_size)

        for i in range(num_part_entries):
            entry_bytes = entries_data[i * part_entry_size : (i + 1) * part_entry_size]
            if len(entry_bytes) < 128:
                break

            type_guid = entry_bytes[0:16]
            if type_guid == b"\x00" * 16:
                continue  # Unused partition entry

            unique_guid = entry_bytes[16:32]
            starting_lba, ending_lba, attributes = struct.unpack("<QQQ", entry_bytes[32:56])
            raw_name = entry_bytes[56:128]
            name = raw_name.decode("utf-16le", errors="ignore").split("\x00")[0].strip()

            if not name or ending_lba < starting_lba:
                continue

            num_sectors = ending_lba - starting_lba + 1
            byte_offset = starting_lba * 512
            byte_size = num_sectors * 512

            partitions[name] = {
                "label": name,
                "start_sector": starting_lba,
                "end_sector": ending_lba,
                "num_sectors": num_sectors,
                "byte_offset": byte_offset,
                "byte_size": byte_size,
                "type_guid": type_guid.hex(),
                "unique_guid": unique_guid.hex(),
            }

        return partitions


def extract_partitions_from_raw_image(
    image_path: Path,
    output_dir: Path,
    partitions: Optional[List[str]] = None,
) -> bool:
    """
    Extract designated partitions from a raw eMMC image into individual .bin files.
    """
    if partitions is None:
        partitions = ALL_CALIBRATION_PARTITIONS

    try:
        gpt = parse_gpt_from_raw_image(image_path)
    except Exception as e:
        print(f"[-] GPT parse error for {image_path}: {e}", file=sys.stderr)
        return False

    output_dir.mkdir(parents=True, exist_ok=True)

    with open(image_path, "rb") as f:
        for part_name in partitions:
            if part_name not in gpt:
                continue
            info = gpt[part_name]
            f.seek(info["byte_offset"])
            data = f.read(info["byte_size"])

            out_file = output_dir / f"{part_name}.bin"
            out_file.write_bytes(data)

    return True


def sanitize_raw_image(
    image_path: Path,
    wipe_partitions: Optional[List[str]] = None,
    clean_rootfs: bool = True,
    dry_run: bool = False,
) -> Tuple[bool, List[Dict]]:
    """
    Wipe unique IMEI, radio calibration, and user data in-place by writing 0x00 bytes.
    Also cleans sensitive rootfs files (.bash_history, ssh known_hosts, logs).
    Makes a raw eMMC dump safe to distribute publicly.
    """
    if dry_run:
        print(f"[DRY-RUN] Simulating sanitization of {image_path.name}...")
        return True, [{"partition": p, "start_sector": 0, "num_sectors": 100, "byte_size": 51200} for p in (wipe_partitions or DEFAULT_SANITIZE_PARTITIONS)]

    if wipe_partitions is None:
        wipe_partitions = DEFAULT_SANITIZE_PARTITIONS

    gpt = parse_gpt_from_raw_image(image_path)
    wiped_summary = []
    chunk_size = 1024 * 1024  # 1 MB chunks
    zero_chunk = b"\x00" * chunk_size

    with open(image_path, "r+b") as f:
        for part_name in wipe_partitions:
            if part_name not in gpt:
                continue
            info = gpt[part_name]
            offset = info["byte_offset"]
            size = info["byte_size"]

            f.seek(offset)
            remaining = size
            while remaining > 0:
                write_size = min(remaining, chunk_size)
                if write_size == chunk_size:
                    f.write(zero_chunk)
                else:
                    f.write(b"\x00" * write_size)
                remaining -= write_size

            wiped_summary.append({
                "partition": part_name,
                "start_sector": info["start_sector"],
                "num_sectors": info["num_sectors"],
                "byte_size": size,
            })

        f.flush()

    # Pass 2: Clean rootfs sensitive files (logs, history) and ensure led-test is installed
    if clean_rootfs:
        clean_rootfs_sensitive_data(image_path, inject_led_test=True, dry_run=dry_run)

    return True, wiped_summary


def find_debugfs() -> Optional[Path]:
    """Find e2fsprogs debugfs binary across platforms."""
    candidates = [
        shutil.which("debugfs"),
        "/opt/homebrew/opt/e2fsprogs/sbin/debugfs",
        "/opt/homebrew/sbin/debugfs",
        "/usr/local/opt/e2fsprogs/sbin/debugfs",
        "/usr/local/sbin/debugfs",
        "/usr/sbin/debugfs",
        "/sbin/debugfs",
    ]
    for c in candidates:
        if c:
            p = Path(c)
            if p.is_file() and os.access(p, os.X_OK):
                return p
    return None


def clean_rootfs_sensitive_data(
    image_path: Path,
    inject_led_test: bool = True,
    dry_run: bool = False,
) -> Tuple[bool, List[str]]:
    """
    Remove sensitive user artifacts (.bash_history, ssh known_hosts, logs)
    directly from the ext4 rootfs partition inside a raw eMMC image using debugfs.
    Also ensures /usr/local/bin/led-test is injected with mode 0755.
    """
    if dry_run:
        print(f"[DRY-RUN] Simulating rootfs sensitive data cleanup on {image_path.name}...")
        return True, ["(dry-run) sensitive files cleaned", "(dry-run) led-test injected"]

    try:
        gpt = parse_gpt_from_raw_image(image_path)
    except Exception as e:
        print(f"[-] Cannot parse GPT for rootfs cleanup: {e}", file=sys.stderr)
        return False, []

    rootfs_info = gpt.get("rootfs") or gpt.get("userdata")
    if not rootfs_info:
        return True, []

    offset = rootfs_info["byte_offset"]
    # Check if partition contains valid ext4 superblock magic (0xef53 at offset 1024 + 0x38)
    try:
        with open(image_path, "rb") as f:
            f.seek(offset + 1080)
            magic = f.read(2)
            if magic != b"\x53\xef":
                return True, []
    except Exception:
        return True, []

    debugfs_bin = find_debugfs()
    if not debugfs_bin:
        print("[!] Warning: debugfs (e2fsprogs) not found. Skipping offline rootfs cleanup.", file=sys.stderr)
        return False, []

    cleaned_items = []
    debugfs_target = f"{image_path}?offset={offset}"

    files_to_remove = [
        "/home/user/.bash_history",
        "/root/.bash_history",
        "/home/user/.ssh/known_hosts",
        "/root/.ssh/known_hosts",
        "/home/user/.ssh/authorized_keys",
        "/root/.ssh/authorized_keys",
        "/var/log/wtmp",
        "/var/log/btmp",
        "/var/log/lastlog",
        "/var/log/auth.log",
        "/var/log/syslog",
        "/var/log/messages",
    ]

    commands = [f"rm {f}" for f in files_to_remove]
    cleaned_items.extend(files_to_remove)

    if inject_led_test:
        repo_root = Path(__file__).resolve().parent.parent
        led_test_script = repo_root / "openstick" / "scripts" / "led-test"
        if led_test_script.exists():
            commands.extend([
                "rm /usr/local/bin/led-test",
                f"write {led_test_script} /usr/local/bin/led-test",
                "set_inode_field /usr/local/bin/led-test mode 0100755",
                "set_inode_field /usr/local/bin/led-test uid 0",
                "set_inode_field /usr/local/bin/led-test gid 0",
            ])
            cleaned_items.append("/usr/local/bin/led-test (injected)")

    cmd_script = "\n".join(commands) + "\n"

    try:
        subprocess.run(
            [str(debugfs_bin), "-w", debugfs_target],
            input=cmd_script,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return True, cleaned_items
    except Exception as e:
        print(f"[-] Error executing debugfs rootfs cleanup: {e}", file=sys.stderr)
        return False, []


def compress_raw_image_to_zip(
    image_path: Path,
    output_zip: Path,
    dry_run: bool = False,
) -> Tuple[bool, Optional[str]]:
    """
    Compress a raw eMMC image (full_emmc.bin) into a zip archive with deflate compression
    and return (success, sha256_hash).
    """
    if dry_run:
        print(f"[DRY-RUN] Simulating compression of {image_path.name} to {output_zip.name}...")
        output_zip.parent.mkdir(parents=True, exist_ok=True)
        output_zip.write_bytes(b"PKmockzip")
        sha_file = output_zip.with_suffix(".zip.sha256")
        sha_file.write_text(f"mocksha256  {output_zip.name}\n")
        return True, "mocksha256"

    import hashlib
    import zipfile

    output_zip.parent.mkdir(parents=True, exist_ok=True)
    temp_zip = output_zip.with_suffix(".tmp.zip")
    if temp_zip.exists():
        temp_zip.unlink()

    print(f"[*] Compressing {image_path.name} into {output_zip.name} (this takes ~1-2 mins)...")
    try:
        with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as zf:
            zf.write(image_path, arcname="full_emmc.bin")

        if output_zip.exists():
            output_zip.unlink()
        shutil.move(str(temp_zip), str(output_zip))

        # Calculate sha256
        print(f"[*] Calculating SHA-256 checksum for {output_zip.name}...")
        hasher = hashlib.sha256()
        with open(output_zip, "rb") as f:
            while c := f.read(65536):
                hasher.update(c)
        digest = hasher.hexdigest()

        sha_file = output_zip.with_suffix(".zip.sha256")
        sha_file.write_text(f"{digest}  {output_zip.name}\n")
        print(f"[+] SHA-256: {digest}")
        return True, digest
    except Exception as e:
        print(f"\n[-] Failed compressing raw image: {e}", file=sys.stderr)
        if temp_zip.exists():
            temp_zip.unlink()
        return False, None


def inject_partitions_into_raw_image(
    image_path: Path,
    calibration_dir: Path,
    partitions: Optional[List[str]] = None,
    dry_run: bool = False,
) -> Tuple[bool, List[str]]:
    """
    Inject personalized calibration partitions in-place into a raw eMMC image.
    Reads .bin or .img files from calibration_dir and writes them to exact GPT offsets.
    """
    if partitions is None:
        partitions = ALL_CALIBRATION_PARTITIONS

    if dry_run:
        print(f"[DRY-RUN] Simulating calibration injection into {image_path.name} from {calibration_dir.name}...")
        return True, partitions

    gpt = parse_gpt_from_raw_image(image_path)
    injected: List[str] = []

    with open(image_path, "r+b") as f:
        for part_name in partitions:
            if part_name not in gpt:
                continue

            # Check for <part_name>.bin or <part_name>.img in calibration_dir
            source_file = calibration_dir / f"{part_name}.bin"
            if not source_file.exists():
                img_candidate = calibration_dir / f"{part_name}.img"
                if img_candidate.exists():
                    source_file = img_candidate

            if not source_file.exists() or source_file.stat().st_size == 0:
                continue

            part_bytes = source_file.read_bytes()
            target_info = gpt[part_name]
            target_size = target_info["byte_size"]

            if len(part_bytes) > target_size:
                print(f"[!] Warning: {source_file.name} ({len(part_bytes)} bytes) exceeds target partition slot ({target_size} bytes). Skipping.", file=sys.stderr)
                continue

            f.seek(target_info["byte_offset"])
            f.write(part_bytes)

            # Pad remainder with zeros if file is smaller than partition slot
            if len(part_bytes) < target_size:
                f.write(b"\x00" * (target_size - len(part_bytes)))

            injected.append(part_name)

        f.flush()

    return True, injected


def _is_file_non_zero(file_path: Path) -> bool:
    """Return True if the file contains at least one non-zero byte."""
    try:
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                if chunk != b"\x00" * len(chunk):
                    return True
    except OSError:
        return False
    return False


# ---------------------------------------------------------------------------
# Backup & Restore Workflows
# ---------------------------------------------------------------------------

def execute_raw_emmc_backup(
    backup_dir: Path,
    calibration_dir: Optional[Path] = None,
    loader: Optional[Path] = None,
    dry_run: bool = False,
) -> bool:
    """
    Execute full raw eMMC clone via EDL:
    edl rf <backup_dir>/full_emmc.bin --memory=eMMC [--loader=<loader>]
    Automatically extracts calibration partitions to:
      1. <backup_dir>/calibration/ (per-run archive)
      2. calibration_dir (active top-level folder)
    """
    backup_dir.mkdir(parents=True, exist_ok=True)
    image_path = backup_dir / "full_emmc.bin"

    if dry_run:
        print(f"[DRY-RUN] Simulating full raw eMMC backup into {image_path}...")
        # Create minimal synthetic raw image for dry-run verification
        create_synthetic_raw_image(image_path)
        archived_calib = backup_dir / "calibration"
        extract_partitions_from_raw_image(image_path, archived_calib)
        if calibration_dir:
            extract_partitions_from_raw_image(image_path, calibration_dir)
        return True

    print(f"[*] Dumping full raw eMMC to: {image_path.name} (this takes ~8-10 minutes)...")
    ok = run_edl_command(["rf", str(image_path)], loader=loader, dry_run=dry_run, timeout=2400)
    if not ok or not image_path.exists():
        print("[-] Full eMMC clone failed or was cancelled.", file=sys.stderr)
        return False

    print("[*] Automatically extracting calibration sidecars from raw eMMC dump...")
    archived_calib = backup_dir / "calibration"
    extract_partitions_from_raw_image(image_path, archived_calib)

    if calibration_dir:
        extract_partitions_from_raw_image(image_path, calibration_dir)
        print(f"[+] Unique device calibration files extracted to: {calibration_dir}")

    return True


def verify_raw_backup(
    backup_dir: Path,
    critical_partitions: Optional[List[str]] = None,
) -> Tuple[bool, Dict]:
    """
    Verify raw eMMC backup and extracted calibration sidecars.
    """
    if critical_partitions is None:
        critical_partitions = DEFAULT_CALIBRATION_PARTITIONS

    image_path = backup_dir / "full_emmc.bin"
    if not image_path.exists():
        return False, {"error": "full_emmc.bin not found in backup directory"}

    try:
        gpt = parse_gpt_from_raw_image(image_path)
    except Exception as e:
        return False, {"error": f"Failed parsing GPT from backup: {e}"}

    meta = gpt.get("__metadata__", {})
    expected_bytes = meta.get("total_bytes", 0)
    actual_bytes = image_path.stat().st_size
    min_required_bytes = max(
        (info["byte_offset"] + info["byte_size"] for k, info in gpt.items() if k != "__metadata__"),
        default=0,
    )

    # Check calibration files in backup_dir/calibration or backup_dir
    calib_dir = backup_dir / "calibration"
    if not calib_dir.exists():
        calib_dir = backup_dir

    verified_partitions = []
    missing_critical = []
    empty_partitions = []

    for cp in critical_partitions:
        cp_file = calib_dir / f"{cp}.bin"
        if not cp_file.exists():
            cp_img = calib_dir / f"{cp}.img"
            if cp_img.exists():
                cp_file = cp_img

        if not cp_file.exists():
            missing_critical.append(cp)
            continue

        size = cp_file.stat().st_size
        if size == 0:
            empty_partitions.append(f"{cp_file.name} (0 bytes)")
            continue

        if cp != "fsc" and not _is_file_non_zero(cp_file):
            empty_partitions.append(f"{cp_file.name} (all zeros / sanitized)")
            continue

        verified_partitions.append({
            "label": cp,
            "filename": cp_file.name,
            "actual_bytes": size,
            "status": "ok",
        })

    is_complete = (
        len(missing_critical) == 0
        and len(empty_partitions) == 0
        and actual_bytes >= min_required_bytes > 0
    )

    report = {
        "directory": str(backup_dir),
        "image_file": image_path.name,
        "image_size_bytes": actual_bytes,
        "image_size_gb": round(actual_bytes / (1024 * 1024 * 1024), 2),
        "gpt_total_bytes": expected_bytes,
        "gpt_partitions_count": len([k for k in gpt if k != "__metadata__"]),
        "verified_partitions": verified_partitions,
        "missing_critical": missing_critical,
        "empty_partitions": empty_partitions,
        "is_complete": is_complete,
    }

    return is_complete, report


def flash_raw_emmc_via_edl(
    image_path: Path,
    calibration_dir: Optional[Path] = None,
    inject_calibration: bool = True,
    loader: Optional[Path] = None,
    dry_run: bool = False,
) -> bool:
    """
    Flash a raw eMMC image via EDL mode:
    1. Injects calibration partitions in-place if requested.
    2. Runs 'edl wf <image_path> --memory=eMMC'.
    3. Runs 'edl reset' to reboot stick.
    """
    if not image_path.exists() and not dry_run:
        print(f"[-] Image file not found: {image_path}", file=sys.stderr)
        return False

    if inject_calibration and calibration_dir:
        print(f"[*] Injecting unique calibration files from {calibration_dir} into {image_path.name}...")
        ok, injected = inject_partitions_into_raw_image(
            image_path=image_path,
            calibration_dir=calibration_dir,
            dry_run=dry_run,
        )
        if ok and injected:
            print(f"[+] Successfully injected {len(injected)} partitions: {', '.join(injected)}")

    print(f"\n[*] Flashing raw eMMC image to stick: {image_path.name}...")
    flash_ok = run_edl_command(["wf", str(image_path)], loader=loader, dry_run=dry_run, timeout=2400)
    if not flash_ok:
        print("[-] Raw image flashing failed.", file=sys.stderr)
        return False

    print("[*] Flashing complete. Rebooting device (edl reset)...")
    run_edl_command(["reset"], loader=loader, dry_run=dry_run)
    return True


def has_valid_calibration(
    calibration_dir: Path,
    critical_partitions: Optional[List[str]] = None,
) -> bool:
    """Check if calibration_dir contains non-empty, non-zeroed files for all critical partitions."""
    if critical_partitions is None:
        critical_partitions = DEFAULT_CALIBRATION_PARTITIONS

    if not calibration_dir.exists():
        return False

    for cp in critical_partitions:
        b_file = calibration_dir / f"{cp}.bin"
        i_file = calibration_dir / f"{cp}.img"
        candidate = b_file if (b_file.exists() and b_file.stat().st_size > 0) else (
            i_file if (i_file.exists() and i_file.stat().st_size > 0) else None
        )
        if candidate is None:
            return False
        if cp != "fsc" and not _is_file_non_zero(candidate):
            return False

    return True


def _is_raw_image_sanitized(image_path: Path, gpt: Dict[str, Dict]) -> bool:
    """Return True if modemst1 is present in GPT and contains only 0x00 bytes."""
    if "modemst1" not in gpt:
        return False
    info = gpt["modemst1"]
    try:
        with open(image_path, "rb") as f:
            f.seek(info["byte_offset"])
            remaining = info["byte_size"]
            while remaining > 0:
                chunk = f.read(min(remaining, 65536))
                if not chunk:
                    break
                if chunk != b"\x00" * len(chunk):
                    return False
                remaining -= len(chunk)
        return True
    except OSError:
        return True


def find_latest_valid_backup(
    project_root: Path,
    device_id: str,
    require_stock: bool = False,
) -> Optional[Path]:
    """
    Find the most recent valid backup directory containing an unsanitized full_emmc.bin.
    Excludes release dump folders ('_release_') and, when require_stock=True,
    prioritizes Stock Android backups (containing 'system' in GPT) over Linux dumps.
    """
    backups_dir = project_root / "backups"
    if not backups_dir.exists():
        return None

    prefix = f"{device_id.lower()}_"

    def _backup_sort_key(d: Path) -> Tuple[str, float, str]:
        # Extract embedded timestamp if present: e.g. YYYYMMDD_HHMMSS
        m = re.search(r"(\d{8}_\d{6})", d.name)
        ts_str = m.group(1) if m else ""
        try:
            mtime = d.stat().st_mtime
        except OSError:
            mtime = 0.0
        return (ts_str, mtime, d.name)

    candidates = sorted(
        [
            d for d in backups_dir.iterdir()
            if d.is_dir()
            and d.name.lower().startswith(prefix)
            and "_release_" not in d.name.lower()
        ],
        key=_backup_sort_key,
        reverse=True,
    )

    valid_candidates: List[Tuple[bool, Path]] = []
    for c in candidates:
        img = c / "full_emmc.bin"
        if not img.exists() or img.stat().st_size == 0:
            continue

        is_stock_layout = False
        try:
            gpt = parse_gpt_from_raw_image(img)
            if _is_raw_image_sanitized(img, gpt):
                continue
            is_stock_layout = "system" in gpt
        except Exception:
            # Allow minimal test files without full GPT if calibration sidecars aren't zeroed
            pass

        calib_subdir = c / "calibration"
        if calib_subdir.exists() and not has_valid_calibration(calib_subdir):
            continue

        valid_candidates.append((is_stock_layout, c))

    if not valid_candidates:
        return None

    if require_stock:
        for is_stock_layout, c in valid_candidates:
            if is_stock_layout:
                return c

    return valid_candidates[0][1]


# ---------------------------------------------------------------------------
# Synthetic GPT Generator for Unit Testing & Dry-Run
# ---------------------------------------------------------------------------

def create_synthetic_raw_image(
    image_path: Path,
    num_total_sectors: int = 7634944,  # ~3.64 GB standard eMMC
    partitions: Optional[List[Tuple[str, int, int]]] = None,
) -> None:
    """
    Generate a minimal synthetic raw eMMC image containing a valid Protective MBR,
    Primary GPT Header, and partition entries array for testing.
    """
    import zlib

    if partitions is None:
        # Compact sector counts for fast unit tests and dry-runs (~2.7 MB file)
        partitions = [
            ("sbl1", 40, 64),
            ("fsc", 4096, 2),
            ("fsg", 4098, 64),
            ("modem", 4200, 128),
            ("modemst1", 4400, 64),
            ("modemst2", 4500, 64),
            ("persist", 4600, 128),
            ("sec", 4800, 32),
            ("boot", 4900, 128),
            ("rootfs", 5100, 256),
        ]

    sector_size = 512
    num_part_entries = 128
    part_entry_size = 128

    # Calculate required image size to contain partition array
    max_sector = max(s + count for _, s, count in partitions)
    header_sectors = 34  # MBR (0) + GPT Header (1) + 32 sectors for 128 entries
    file_sectors = max(max_sector, header_sectors + 64)

    image_path.parent.mkdir(parents=True, exist_ok=True)
    with open(image_path, "wb") as f:
        # Write empty file up to file_sectors
        f.seek(file_sectors * sector_size - 1)
        f.write(b"\x00")

        # 1. Protective MBR (Sector 0)
        f.seek(0)
        mbr = bytearray(512)
        mbr[510:512] = b"\x55\xAA"
        # Partition 1 entry in MBR (offset 446)
        mbr[446 + 4] = 0xEE  # GPT Protective partition type
        struct.pack_into("<I", mbr, 446 + 8, 1)  # Starting LBA 1
        struct.pack_into("<I", mbr, 446 + 12, min(0xFFFFFFFF, num_total_sectors - 1))
        f.write(mbr)

        # 2. Build Partition Entries Array (Sector 2, offset 1024)
        entries_buf = bytearray(num_part_entries * part_entry_size)
        type_guid = bytes.fromhex("ebd0a0a2b9e5443387c068b6b72699c7")  # Basic Data
        for i, (name, start, count) in enumerate(partitions):
            entry = bytearray(part_entry_size)
            entry[0:16] = type_guid
            entry[16:32] = bytes.fromhex(f"{i:032x}")
            end = start + count - 1
            struct.pack_into("<QQQ", entry, 32, start, end, 0)
            name_utf16 = name.encode("utf-16le")[:72]
            entry[56 : 56 + len(name_utf16)] = name_utf16
            entries_buf[i * part_entry_size : (i + 1) * part_entry_size] = entry

        entries_crc = zlib.crc32(entries_buf) & 0xFFFFFFFF

        # 3. Primary GPT Header (Sector 1, offset 512)
        f.seek(512)
        gpt_header = bytearray(512)
        struct.pack_into("<8s", gpt_header, 0, b"EFI PART")
        struct.pack_into("<4s", gpt_header, 8, b"\x00\x00\x01\x00")
        struct.pack_into("<I", gpt_header, 12, 92)  # Header size
        struct.pack_into("<Q", gpt_header, 24, 1)   # Current LBA
        struct.pack_into("<Q", gpt_header, 32, num_total_sectors - 1)  # Backup LBA
        struct.pack_into("<Q", gpt_header, 40, 34)  # First usable LBA
        struct.pack_into("<Q", gpt_header, 48, num_total_sectors - 34)  # Last usable LBA
        struct.pack_into("<Q", gpt_header, 72, 2)   # Partition entries LBA
        struct.pack_into("<I", gpt_header, 80, num_part_entries)
        struct.pack_into("<I", gpt_header, 84, part_entry_size)
        struct.pack_into("<I", gpt_header, 88, entries_crc)
        header_crc = zlib.crc32(gpt_header[:92]) & 0xFFFFFFFF
        struct.pack_into("<I", gpt_header, 16, header_crc)
        f.write(gpt_header)

        # Write Partition Entries Array
        f.seek(1024)
        f.write(entries_buf)

        # Write dummy data into partition sectors
        for name, start, count in partitions:
            f.seek(start * sector_size)
            # Write identifying tag inside the partition
            tag = f"PARTITION_{name.upper()}".encode("ascii")
            f.write((tag * ((count * sector_size // len(tag)) + 1))[: count * sector_size])
