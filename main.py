#!/usr/bin/env python3
"""
OpenStick Installer
Cross-platform utility to backup stock partitions and install Linux on MSM8916 USB sticks.
"""

import argparse
import datetime
import shutil
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

# Ensure package root is in python path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from openstick.bootstrap import ensure_environment
from openstick.devices import get_device_by_id, DeviceModel
from openstick.ui import (
    print_banner,
    show_board_menu,
    show_device_info,
    prompt_backup_partitions,
    show_adb_guidance,
    show_backup_summary,
    show_action_menu,
    show_post_install_info,
    format_size,
)
from openstick import adb
from openstick import edl
from openstick import network
from openstick import releases


def ensure_device_in_edl(device: DeviceModel, dry_run: bool = False) -> bool:
    """Ensure the device is connected in Qualcomm 9008 EDL mode."""
    if dry_run or edl.is_edl_connected():
        print("[+] Device is already in Qualcomm 9008 EDL mode.")
        return True

    if not adb.is_adb_available():
        print("[-] 'adb' command was not found in your system PATH.", file=sys.stderr)
        print("    If your stick is in Android, please install ADB or enter EDL via the physical button.", file=sys.stderr)

    adb_dev = adb.wait_for_device(timeout=5)
    while not adb_dev and not edl.is_edl_connected():
        stick = network.find_stick_device(dry_run=dry_run)
        if stick:
            ip, banner = stick
            print(f"[+] Found OpenStick running Linux at {ip} ({banner})")
            print("    To enter EDL mode: Unplug the stick, hold down the physical recovery button, and plug into USB.")
        else:
            show_adb_guidance(device)
        try:
            retry = input("Press [Enter] to scan again, or 'q' to cancel: ").strip().lower()
            if retry in ("q", "quit", "cancel"):
                return False
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            return False

        if edl.is_edl_connected():
            print("[+] Qualcomm 9008 EDL device detected!")
            return True

        adb_dev = adb.wait_for_device(timeout=5)

    if edl.is_edl_connected():
        return True

    if adb_dev:
        print(f"[+] Found ADB device: {adb_dev.serial} (State: {adb_dev.state})")
        print("[*] Preparing root privileges on device...")
        adb.prepare_root(adb_dev.serial)

        print("[*] Rebooting device into Qualcomm EDL mode (9008)...")
        if not adb.reboot_to_edl(adb_dev.serial, dry_run=dry_run):
            print("[-] Failed to issue reboot command via ADB.", file=sys.stderr)
            return False

        return edl.wait_for_edl(timeout=30, dry_run=dry_run)

    return False


def handle_partition_backup(device: DeviceModel, dry_run: bool = False) -> Tuple[bool, Optional[Path]]:
    """Handle ADB reboot to EDL and complete raw eMMC + calibration backup flow."""
    print("\n[*] Initializing partition backup sequence...")

    if not ensure_device_in_edl(device, dry_run=dry_run):
        print("[-] Could not enter Qualcomm 9008 EDL mode for backup.", file=sys.stderr)
        return False, None

    # Prepare timestamped backup directory
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backups_root = (PROJECT_ROOT / ".cache" / "dry_run_backups") if dry_run else (PROJECT_ROOT / "backups")
    backup_dir = backups_root / f"{device.id}_{timestamp}"
    calibration_dir = (PROJECT_ROOT / ".cache" / "dry_run_calibration") if dry_run else (PROJECT_ROOT / "calibration")
    loader = edl.resolve_loader(device.recommended_loader)

    print(f"[*] Target backup destination: {backup_dir.relative_to(PROJECT_ROOT) if not dry_run else backup_dir}")
    if loader:
        print(f"[*] Using Firehose programmer: {loader.name}")

    # Execute full raw eMMC clone and automatic calibration extraction
    success = edl.execute_raw_emmc_backup(
        backup_dir=backup_dir,
        calibration_dir=calibration_dir,
        loader=loader,
        dry_run=dry_run,
    )

    if success:
        is_complete, report = edl.verify_raw_backup(
            backup_dir=backup_dir,
            critical_partitions=device.critical_partitions,
        )
        show_backup_summary(report, calibration_dir=calibration_dir)
        return is_complete, backup_dir
    else:
        print("[-] Backup failed or was interrupted.", file=sys.stderr)
        return False, None


def handle_linux_install(
    device: DeviceModel,
    dry_run: bool = False,
) -> bool:
    """Download general-purpose Linux image, inject calibration, and flash via EDL."""
    print("\n" + "=" * 65)
    print(f"       INSTALLING OPENSTICK LINUX (DEBIAN) FOR {device.name.split()[0].upper()}")
    print("=" * 65)

    calibration_dir = (PROJECT_ROOT / ".cache" / "dry_run_calibration") if dry_run else (PROJECT_ROOT / "calibration")
    loader = edl.resolve_loader(device.recommended_loader)

    # 1. Safety check: ensure calibration files exist
    if not edl.has_valid_calibration(calibration_dir, device.critical_partitions) and not dry_run:
        print(f"[!] Critical calibration files not detected in: {calibration_dir}")
        # Try checking previous backups
        latest_backup = edl.find_latest_valid_backup(PROJECT_ROOT, device.id)
        if latest_backup:
            print(f"[*] Found previous backup in {latest_backup.name}. Extracting calibration files...")
            edl.extract_partitions_from_raw_image(latest_backup / "full_emmc.bin", calibration_dir)

        if not edl.has_valid_calibration(calibration_dir, device.critical_partitions):
            print("[-] Unable to locate critical calibration files (modemst1, modemst2, fsg, fsc, persist, sec).", file=sys.stderr)
            print("    Please run the backup step or place your partition files into calibration/ first.", file=sys.stderr)
            return False

    # 2. Fetch latest release from GitHub
    if not dry_run:
        print(f"[*] Fetching latest firmware releases from GitHub ({releases.DEFAULT_GITHUB_REPO})...")
        release = releases.get_latest_release()
        if not release:
            print("[-] Could not reach GitHub Releases API or no published releases found.", file=sys.stderr)
            return False
        release_tag = release.get("tag_name", "latest")
    else:
        print(f"[DRY-RUN] Simulating GitHub Releases fetch ({releases.DEFAULT_GITHUB_REPO})...")
        release_tag = "v0.1.0"
        release = {
            "tag_name": release_tag,
            "assets": [
                {"name": f"openstick-{device.id}-linux.zip", "browser_download_url": "mock://", "size": 150000000}
            ]
        }
    print(f"[+] Found release: '{release_tag}'")

    # 3. Find matching Linux asset
    asset = releases.find_matching_asset(release, device.id, mode="linux") if release else None
    if not asset and not dry_run:
        print(f"[-] No matching Linux image found in release '{release_tag}' for board '{device.id}'.", file=sys.stderr)
        print("    Expected asset name like: openstick-uz801-linux.zip or openstick-uz801-debian.zip", file=sys.stderr)
        return False

    if not asset and dry_run:
        asset = {"name": f"openstick-{device.id}-linux.zip", "browser_download_url": "mock://", "size": 150000000}

    # 4. Download and extract image asset
    ok, extracted_dir = releases.download_and_extract_asset(
        asset=asset,
        tag_name=release_tag,
        project_root=PROJECT_ROOT,
        mode="linux",
        dry_run=dry_run,
    )
    if not ok or not extracted_dir:
        print("[-] Failed downloading or extracting Linux release.", file=sys.stderr)
        return False

    # 5. Locate raw eMMC image in extracted folder
    raw_image = releases.find_raw_image_in_dir(extracted_dir)
    if not raw_image and not dry_run:
        print(f"[-] No raw eMMC image (full_emmc.bin) found inside {extracted_dir.name}.", file=sys.stderr)
        return False

    if not raw_image and dry_run:
        raw_image = extracted_dir / "full_emmc.bin"
        if not raw_image.exists():
            edl.create_synthetic_raw_image(raw_image)

    # 6. Ensure device is in EDL mode
    if not ensure_device_in_edl(device, dry_run=dry_run):
        print("[-] Device must be in Qualcomm 9008 EDL mode to flash.", file=sys.stderr)
        return False

    # 7. Inject calibration in-place and flash raw image via EDL
    flash_ok = edl.flash_raw_emmc_via_edl(
        image_path=raw_image,
        calibration_dir=calibration_dir,
        inject_calibration=True,
        loader=loader,
        dry_run=dry_run,
    )

    if flash_ok:
        detected_ip = network.wait_for_debian_boot(timeout=60, dry_run=dry_run)
        show_post_install_info("linux", detected_ip=detected_ip)
        return True
    return False


def handle_stock_recovery(
    device: DeviceModel,
    dry_run: bool = False,
) -> bool:
    """Restore stock factory firmware from backups/ via EDL."""
    print("\n" + "=" * 65)
    print(f"       RESTORING STOCK FACTORY BACKUP FOR {device.name.split()[0].upper()}")
    print("=" * 65)

    loader = edl.resolve_loader(device.recommended_loader)

    # 1. Locate latest backup with full_emmc.bin
    backup_dir = edl.find_latest_valid_backup(PROJECT_ROOT, device.id, require_stock=True)
    if not backup_dir and not dry_run:
        print("[-] No valid full_emmc.bin backup found in backups/.", file=sys.stderr)
        return False

    if dry_run and not backup_dir:
        backup_dir = PROJECT_ROOT / ".cache" / "dry_run_backups" / f"{device.id}_mock"
        backup_dir.mkdir(parents=True, exist_ok=True)
        edl.create_synthetic_raw_image(backup_dir / "full_emmc.bin")

    image_path = backup_dir / "full_emmc.bin"
    print(f"[*] Found backup: {image_path.relative_to(PROJECT_ROOT) if not dry_run else image_path.name}")

    # 2. Ensure device is in EDL mode
    if not ensure_device_in_edl(device, dry_run=dry_run):
        print("[-] Device must be in Qualcomm 9008 EDL mode to restore backup.", file=sys.stderr)
        return False

    # 3. Flash full backup image directly (no injection needed as it already has original calibration)
    flash_ok = edl.flash_raw_emmc_via_edl(
        image_path=image_path,
        inject_calibration=False,
        loader=loader,
        dry_run=dry_run,
    )

    if flash_ok:
        show_post_install_info("stock")
        return True
    return False


def handle_create_release_image(
    device: DeviceModel,
    dry_run: bool = False,
) -> bool:
    """Dump full raw eMMC from device in EDL, sanitize sensitive data, and package release zip."""
    print("\n" + "=" * 65)
    print(f"       CREATING SANITIZED RELEASE IMAGE FOR {device.name.split()[0].upper()}")
    print("=" * 65)

    if not ensure_device_in_edl(device, dry_run=dry_run):
        print("[-] Device must be in Qualcomm 9008 EDL mode to dump eMMC.", file=sys.stderr)
        return False

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = (PROJECT_ROOT / ".cache" / "dry_run_backups" / f"{device.id}_release_{timestamp}") if dry_run else (PROJECT_ROOT / "backups" / f"{device.id}_release_{timestamp}")
    calibration_dir = (PROJECT_ROOT / ".cache" / "dry_run_calibration") if dry_run else (PROJECT_ROOT / "calibration")
    loader = edl.resolve_loader(device.recommended_loader)

    print(f"[*] Target backup destination: {backup_dir.name}")
    success = edl.execute_raw_emmc_backup(
        backup_dir=backup_dir,
        calibration_dir=calibration_dir,
        loader=loader,
        dry_run=dry_run,
    )

    if not success:
        print("[-] eMMC dump failed or was cancelled.", file=sys.stderr)
        return False

    raw_image = backup_dir / "full_emmc.bin"
    if not raw_image.exists():
        print(f"[-] Dump file not found: {raw_image}", file=sys.stderr)
        return False

    # Reboot device back so it is not stuck in EDL mode
    print("[*] eMMC dump complete. Rebooting device (edl reset)...")
    edl.run_edl_command(["reset"], loader=loader, dry_run=dry_run)

    print("\n[*] Sanitizing raw eMMC dump offline...")
    print("    - Zeroing unique IMEI, radio calibration, and private data partitions...")
    print("    - Cleaning rootfs command history, SSH keys, and system logs...")
    print("    - Ensuring /usr/local/bin/led-test is installed in rootfs...")
    ok, summary = edl.sanitize_raw_image(raw_image, clean_rootfs=True, dry_run=dry_run)
    if not ok:
        print("[-] Sanitization failed.", file=sys.stderr)
        return False

    print("\n[+] Offline sanitization completed successfully!")
    print("-" * 65)
    print(f"{'Partition':<16} {'Start Sector':<14} {'Sectors':<12} {'Size':<10}")
    print("-" * 65)
    for s in summary:
        print(f"{s['partition']:<16} {s['start_sector']:<14} {s['num_sectors']:<12} {format_size(s['byte_size']):<10}")
    print("-" * 65)

    # Package into dist/
    dist_dir = (PROJECT_ROOT / ".cache" / "dry_run_dist") if dry_run else (PROJECT_ROOT / "dist")
    zip_path = dist_dir / f"openstick-{device.id}-linux.zip"
    print(f"\n[*] Packaging sanitized firmware into {zip_path.name}...")
    compress_ok, digest = edl.compress_raw_image_to_zip(
        image_path=raw_image,
        output_zip=zip_path,
        dry_run=dry_run,
    )

    if not compress_ok:
        print("[-] Packaging release zip failed.", file=sys.stderr)
        return False

    # Also update local cache if cached releases exist
    releases_cache_root = PROJECT_ROOT / ".cache" / "releases"
    if releases_cache_root.exists() and not dry_run:
        for cached_tag_dir in releases_cache_root.iterdir():
            if not cached_tag_dir.is_dir():
                continue
            local_cached_img = cached_tag_dir / f"openstick-{device.id}-linux" / "full_emmc.bin"
            if local_cached_img.parent.exists():
                try:
                    print(f"[*] Updating local release cache at {cached_tag_dir.name}/{local_cached_img.parent.name}...")
                    shutil.copy2(str(raw_image), str(local_cached_img))
                except Exception:
                    pass

    print("\n" + "=" * 65)
    print("       RELEASE IMAGE GENERATION COMPLETED SUCCESSFULLY")
    print("=" * 65)
    print(f"  • Image Archive:  {zip_path.relative_to(PROJECT_ROOT) if not dry_run else zip_path.name} ({format_size(zip_path.stat().st_size) if zip_path.exists() else 'N/A'})")
    print(f"  • SHA-256 Digest: {digest}")
    print(f"  • Calibration:    Saved safely in {calibration_dir.relative_to(PROJECT_ROOT) if not dry_run else calibration_dir.name}/")
    print("  • Includes:       /usr/local/bin/led-test pre-installed")
    print("=" * 65 + "\n")
    return True


def handle_sanitize_image(image_path_str: str) -> bool:
    """Sanitize a raw eMMC image dump for public release."""
    image_path = Path(image_path_str).resolve()
    if not image_path.exists():
        print(f"[-] Image file not found: {image_path}", file=sys.stderr)
        return False

    print("\n" + "=" * 65)
    print("           RAW eMMC IMAGE SANITIZATION UTILITY")
    print("=" * 65)
    print(f"Target image: {image_path}")
    print("[*] Zeroing out IMEI, radio calibration, and private data partitions...")

    ok, summary = edl.sanitize_raw_image(image_path)
    if ok:
        print("\n[+] Sanitization completed successfully!")
        print("-" * 65)
        print(f"{'Partition':<16} {'Start Sector':<14} {'Sectors':<12} {'Size':<10}")
        print("-" * 65)
        for s in summary:
            print(f"{s['partition']:<16} {s['start_sector']:<14} {s['num_sectors']:<12} {format_size(s['byte_size']):<10}")
        print("-" * 65)
        print(f"[+] {image_path.name} is now clean and ready to compress for GitHub Releases.\n")
        return True
    return False


def main():
    parser = argparse.ArgumentParser(description="OpenStick MSM8916 Linux Installer")
    parser.add_argument("--dry-run", action="store_true", help="Simulate execution without modifying hardware")
    parser.add_argument("--skip-bootstrap", action="store_true", help="Skip virtual environment bootstrap check")
    parser.add_argument("--board", "--model", type=str, help="Specify board directly (e.g. uz801)")
    parser.add_argument("--sanitize-image", type=str, help="Zero out unique partitions from a full_emmc.bin image")
    parser.add_argument("--create-release", action="store_true", help="Dump raw eMMC, sanitize, and package new release zip")
    parser.add_argument("--find", action="store_true", help="Scan network to find connected OpenStick running Linux")
    args = parser.parse_args()

    # Sanitizer CLI flag
    if args.sanitize_image:
        success = handle_sanitize_image(args.sanitize_image)
        sys.exit(0 if success else 1)

    # Bootstrap virtual environment automatically if not already running in one
    if not args.skip_bootstrap and not args.dry_run:
        ensure_environment(project_root=PROJECT_ROOT, dry_run=args.dry_run)

    print_banner()

    # Create release image CLI flag
    if args.create_release:
        board_id = args.board or "uz801"
        dev = get_device_by_id(board_id)
        if not dev:
            print(f"[-] Unknown board: '{board_id}'. Currently supporting: 'uz801'.", file=sys.stderr)
            sys.exit(1)
        success = handle_create_release_image(dev, dry_run=args.dry_run)
        sys.exit(0 if success else 1)

    # Network scanner CLI flag
    if args.find:
        print("\n[*] Scanning network interfaces for connected OpenStick device...")
        result = network.find_stick_device(dry_run=args.dry_run)
        if result:
            ip, banner = result
            network.print_discovery_summary(ip=ip, banner=banner)
        else:
            network.print_discovery_summary(ip=None)
        return

    # Step 1: Board Selection
    if args.board:
        device = get_device_by_id(args.board)
        if not device:
            print(f"[-] Unknown board: '{args.board}'. Currently supporting: 'uz801'.", file=sys.stderr)
            sys.exit(1)
    else:
        device = show_board_menu()
        if device is None:
            # User chose "Other board" and received GitHub issue instructions
            sys.exit(0)

    show_device_info(device)

    # Step 2: Stock Partition Backup
    do_backup = prompt_backup_partitions()
    if do_backup:
        backup_ok, backup_dir = handle_partition_backup(device, dry_run=args.dry_run)
        if not backup_ok:
            print("[!] Backup completed with warnings or failed. Check the logs above.")
        else:
            print("[+] Backup finished successfully!")
    else:
        print("\n[*] Skipping partition backup at user request.")
        calibration_dir = (PROJECT_ROOT / ".cache" / "dry_run_calibration") if args.dry_run else (PROJECT_ROOT / "calibration")
        if edl.has_valid_calibration(calibration_dir, device.critical_partitions):
            print(f"[+] Found existing calibration partitions in: {calibration_dir.resolve()}")
        else:
            latest_backup = edl.find_latest_valid_backup(PROJECT_ROOT, device.id)
            if latest_backup:
                print(f"[+] Found existing backup in: {latest_backup.name}")
                edl.extract_partitions_from_raw_image(latest_backup / "full_emmc.bin", calibration_dir)

    # Step 3: Action Selection (Install Linux vs. Restore Stock Backup vs. Create Release vs. Exit)
    action = show_action_menu(device)
    if action == "linux":
        handle_linux_install(device, dry_run=args.dry_run)
    elif action == "stock":
        handle_stock_recovery(device, dry_run=args.dry_run)
    elif action == "release":
        handle_create_release_image(device, dry_run=args.dry_run)
    else:
        print("\n[+] Exiting installer. Your backups and calibration files are saved.")
        sys.exit(0)


if __name__ == "__main__":
    main()
