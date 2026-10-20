"""Qualcomm EDL (Emergency Download / 9008 mode) and raw eMMC image engine."""

import os
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
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
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
) -> Tuple[bool, List[Dict]]:
    """
    Wipe unique IMEI, radio calibration, and user data in-place by writing 0x00 bytes.
    Makes a raw eMMC dump safe to distribute publicly.
    """
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

    return True, wiped_summary


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
        archived_calib.mkdir(parents=True, exist_ok=True)
        for p in DEFAULT_CALIBRATION_PARTITIONS:
            (archived_calib / f"{p}.bin").write_bytes(b"\x01" * 1024)
        if calibration_dir:
            calibration_dir.mkdir(parents=True, exist_ok=True)
            for p in DEFAULT_CALIBRATION_PARTITIONS:
                (calibration_dir / f"{p}.bin").write_bytes(b"\x01" * 1024)
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
            empty_partitions.append(f"{cp}.bin (0 bytes)")
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
        and actual_bytes > 0
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
    """Check if calibration_dir contains non-empty files for all critical partitions."""
    if critical_partitions is None:
        critical_partitions = DEFAULT_CALIBRATION_PARTITIONS

    if not calibration_dir.exists():
        return False

    for cp in critical_partitions:
        b_file = calibration_dir / f"{cp}.bin"
        i_file = calibration_dir / f"{cp}.img"
        valid = (b_file.exists() and b_file.stat().st_size > 0) or (i_file.exists() and i_file.stat().st_size > 0)
        if not valid:
            return False

    return True


def find_latest_valid_backup(project_root: Path, device_id: str) -> Optional[Path]:
    """Find the most recent valid backup directory containing full_emmc.bin."""
    backups_dir = project_root / "backups"
    if not backups_dir.exists():
        return None

    candidates = sorted(
        [d for d in backups_dir.iterdir() if d.is_dir() and d.name.lower().startswith(f"{device_id.lower()}_")],
        key=lambda x: x.name,
        reverse=True,
    )

    for c in candidates:
        if (c / "full_emmc.bin").exists() and (c / "full_emmc.bin").stat().st_size > 0:
            return c

    return None


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
    if partitions is None:
        # (label, start_sector, num_sectors)
        partitions = [
            ("sbl1", 40, 1024),
            ("fsc", 4096, 2),
            ("fsg", 4098, 3072),
            ("modem", 7170, 131072),
            ("modemst1", 138242, 3072),
            ("modemst2", 141314, 3072),
            ("persist", 144386, 65536),
            ("sec", 209922, 32),
            ("boot", 209954, 65536),
            ("rootfs", 275490, 4194304),
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

        # 2. Primary GPT Header (Sector 1, offset 512)
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
        f.write(gpt_header)

        # 3. Partition Entries Array (Sector 2, offset 1024)
        f.seek(1024)
        type_guid = bytes.fromhex("ebd0a0a2b9e5443387c068b6b72699c7")  # Basic Data
        for i, (name, start, count) in enumerate(partitions):
            entry = bytearray(part_entry_size)
            entry[0:16] = type_guid
            entry[16:32] = bytes.fromhex(f"{i:032x}")
            end = start + count - 1
            struct.pack_into("<QQQ", entry, 32, start, end, 0)
            name_utf16 = name.encode("utf-16le")[:72]
            entry[56 : 56 + len(name_utf16)] = name_utf16
            f.seek(1024 + i * part_entry_size)
            f.write(entry)

        # Write dummy data into partition sectors
        for name, start, count in partitions:
            f.seek(start * sector_size)
            # Write identifying tag inside the partition
            tag = f"PARTITION_{name.upper()}".encode("ascii")
            f.write((tag * ((count * sector_size // len(tag)) + 1))[: count * sector_size])
