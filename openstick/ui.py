"""User Interface helpers and menu presentation for OpenStick Installer."""

import sys
from pathlib import Path
from typing import Dict, List, Optional
from openstick import __version__
from openstick.devices import (
    CUSTOM_DEVICE,
    DeviceModel,
    get_device_by_id,
    get_device_by_index,
    get_supported_devices,
)


def print_disclaimer():
    """Display safety disclaimer and liability waiver."""
    print("=" * 65)
    print("                    WARNING & DISCLAIMER")
    print("=" * 65)
    print("  Flashing Linux or third-party firmware onto your device is a")
    print("  risky process that carries inherent risks of device bricking,")
    print("  hardware damage, or permanent data loss.")
    print("")
    print("  The script authors and contributors are NOT responsible for")
    print("  any bricked devices, lost cellular functionality, data loss,")
    print("  or any other outcomes resulting from the use of this tool.")
    print("  PROCEED ENTIRELY AT YOUR OWN RISK.")
    print("=" * 65 + "\n")


def show_flashing_warning(mode: str = "linux"):
    """Display prominent risk warning before flashing firmware."""
    target = "Linux" if mode == "linux" else "firmware"
    print("\n" + "!" * 65)
    print(f" [!] WARNING: Flashing {target} is a risky process that directly")
    print("     modifies low-level eMMC partitions.")
    print("     The script authors are NOT responsible for any bricked devices,")
    print("     loss of IMEI / calibration data, or other adverse outcomes.")
    print("     Proceed entirely at your own risk.")
    print("!" * 65 + "\n")


def print_banner():
    """Print welcoming ASCII banner and safety disclaimer."""
    banner = rf"""
   ___                   ____  _   _      _    
  / _ \ _ __   ___ _ __ / ___|| |_(_) ___| | __
 | | | | '_ \ / _ \ '_ \\___ \| __| |/ __| |/ /
 | |_| | |_) |  __/ | | |___) | |_| | (__|   < 
  \___/| .__/ \___|_| |_|____/ \__|_|\___|_|\_\
       |_|  MSM8916 Linux Installer v{__version__}
=====================================================
"""
    print(banner)
    print_disclaimer()


def show_board_menu() -> DeviceModel:
    """
    Display initial board selection menu for all supported devices plus 'Custom image'.
    Returns selected DeviceModel.
    """
    devices = list(get_supported_devices().values())
    custom_idx = len(devices) + 1

    print("\n[+] Step 1: Select your target board")
    print("-" * 55)
    for idx, dev in enumerate(devices, start=1):
        print(f"  [{idx}] {dev.name} - Qualcomm MSM8916")
    print(f"  [{custom_idx}] Custom image")
    print("-" * 55)

    while True:
        try:
            choice = input(f"Please select board [1-{custom_idx}] or 'q' to quit: ").strip().lower()
            if choice in ("q", "quit", "exit"):
                print("Exiting.")
                sys.exit(0)

            if choice.isdigit():
                num = int(choice)
                if num == custom_idx:
                    return CUSTOM_DEVICE
                dev = get_device_by_index(num)
                if dev is not None:
                    return dev
            elif choice in ("custom", "custom-image", "custom_image", "other"):
                return CUSTOM_DEVICE
            else:
                dev = get_device_by_id(choice)
                if dev is not None:
                    return dev

            board_hints = ", ".join(f"{i} for {d.id.upper()}" for i, d in enumerate(devices, start=1))
            print(f"[-] Invalid selection. Enter {board_hints}, or {custom_idx} for Custom image.")
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(1)


def show_other_board_message():
    """Display GitHub issue guidance when user chooses 'Other board'."""
    board_names = [d.id.upper() for d in get_supported_devices().values()]
    if len(board_names) > 1:
        supported_str = ", ".join(board_names[:-1]) + f" and {board_names[-1]} boards"
    elif board_names:
        supported_str = f"{board_names[0]} board"
    else:
        supported_str = "MSM8916 boards"

    print("\n" + "=" * 68)
    print("                     BOARD SUPPORT REQUEST")
    print("=" * 68)
    print(f"Currently, OpenStick Installer officially supports the {supported_str}.")
    print("We are actively expanding support for additional MSM8916 boards!\n")
    print("Please open a GitHub issue to request support for your board:")
    print("  -> https://github.com/Basistiy/openstick-installer/issues\n")
    print("Helpful details to include in your issue:")
    print("  - Board name / model printed on the casing")
    print("  - PCB silk markings / revision (e.g. UZ801-V3, HMUF02-V05, SP970, MF70, etc.)")
    print("  - High-resolution photos of both sides of the board")
    print("=" * 68 + "\n")


def show_device_info(device: DeviceModel):
    """Display summary and notes for the selected device."""
    print("\n" + "=" * 60)
    print(f" Selected Device: {device.name}")
    print("=" * 60)
    print(f"  - SoC:              {device.soc}")
    print(f"  - RAM / Storage:    {device.ram} / {device.storage}")
    print(f"  - Default Web UI:   {device.adb_enable_url}")
    print(f"  - Firehose Loader:  {device.recommended_loader}")
    print("\nImportant Notes:")
    for note in device.notes:
        print(f"  - {note}")
    print("=" * 60 + "\n")


def prompt_backup_partitions() -> bool:
    """Ask user if they want to copy all original partitions."""
    print("\n[+] Step 2: Stock Partition Backup")
    print("=" * 60)
    print("Backing up your stock eMMC partitions is STRONGLY RECOMMENDED.")
    print("Partitions like 'modemst1', 'modemst2', 'fsg', and 'fsc' contain your")
    print("stick's unique IMEI and cellular calibration data.")
    print("=" * 60)

    try:
        choice = input("\nDo you want to backup original partitions now? [Y/n]: ").strip().lower()
        if not choice:
            return True
        return choice in ("y", "yes")
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        sys.exit(1)


def show_adb_guidance(device: DeviceModel):
    """Show guidance when device is not in EDL mode and no software interface was found."""
    print("\n" + "!" * 65)
    print("       Device not detected in EDL, Fastboot, or ADB Mode")
    print("!" * 65)
    print("To enter Emergency Download (EDL / 9008) mode:")
    print("\nHardware Option (Recommended / Most Reliable):")
    print("  1. Unplug the stick from USB.")
    print("  2. Hold down the physical recovery/reset button on the board,")
    print("     or short the two EDL test pins/pads with tweezers.")
    print("  3. While holding the button or shorting pins, plug into USB.")
    print("  4. Release the button / pins after 3 seconds (lands directly in 9008).")
    print("\nSoftware Options:")
    print("  - If stick is running Android:")
    print("    1. Plug stick into USB and verify if 'adb devices' detects it.")
    print("       (Many factory sticks have ADB enabled by default out of the box!)")
    print(f"    2. If not detected, connect PC to stick's Wi-Fi network and check web panel")
    print(f"       ({device.adb_enable_url} or /usbdebug.html) to enable USB debugging.")
    print("    3. Plug stick into USB - installer will reboot it automatically.")
    print("  - If stick is running Linux (Debian):")
    print("    1. SSH to the stick:  ssh user@192.168.5.1  (Password: 1)")
    print("    2. Run command:       sudo systemctl reboot bootloader")
    print("    3. The installer will catch it in Fastboot and reboot into EDL mode.")
    print("  - If stick is in Fastboot mode:")
    print("    Run command:         fastboot oem reboot-edl")
    print("!" * 65 + "\n")


def format_size(bytes_val: int) -> str:
    """Format bytes into a human-readable string."""
    if bytes_val >= 1024 * 1024 * 1024:
        return f"{bytes_val / (1024 * 1024 * 1024):.2f} GB"
    elif bytes_val >= 1024 * 1024:
        return f"{bytes_val / (1024 * 1024):.2f} MB"
    elif bytes_val >= 1024:
        return f"{bytes_val / 1024:.2f} KB"
    return f"{bytes_val} B"


def show_backup_summary(report: dict, calibration_dir: Optional[Path] = None):
    """Display clean summary after partition backup."""
    print("\n" + "*" * 65)
    print("                    BACKUP VERIFICATION SUMMARY")
    print("*" * 65)
    print(f"  - Backup Directory:   {report.get('directory')}")
    if report.get("imei"):
        print(f"  - Modem IMEI:         {report.get('imei')}")
    actual_gb = report.get('image_size_gb', 0.0)
    gpt_total = report.get('gpt_total_bytes', 0)
    gpt_str = f" / {format_size(gpt_total)} eMMC" if gpt_total > 0 else ""
    print(f"  - Full eMMC Clone:    {report.get('image_file')} ({actual_gb} GB{gpt_str})")
    print(f"  - Total Partitions:   {report.get('gpt_partitions_count')}")
    if calibration_dir:
        print(f"  - Active Calibration: {calibration_dir.resolve()}")

    verified = report.get("verified_partitions", [])
    if verified:
        print("\n  Extracted Calibration Sidecars:")
        for part in verified:
            label = part.get("label", "")
            actual = format_size(part.get("actual_bytes", 0))
            print(f"    [+] {label:<16} : {actual:>9}")

    missing = report.get("missing_critical", [])
    if missing:
        print(f"\n  [!] WARNING: Missing calibration partitions: {', '.join(missing)}")
    else:
        print("\n  [+] All unique cellular calibration partitions successfully backed up!")

    print("*" * 65 + "\n")


def show_action_menu(device: DeviceModel) -> str:
    """Display interactive action menu."""
    print("\n[+] Step 3: Choose Next Action")
    print("-" * 65)
    print("  [1] Install Linux (Debian) [Recommended]")
    if device.id == "custom":
        print("      Flashes a custom raw eMMC Linux image (.bin or .zip),")
        print("      injects your unique calibration partitions, and flashes via EDL.")
    else:
        print(f"      Downloads universal Linux image for {device.name.split()[0]},")
        print("      injects your unique calibration partitions, and flashes via EDL.")
    print("  [2] Restore Stock Backup")
    print(f"      Flashes your original raw eMMC backup from backups/ to restore Android.")
    print("  [3] Create Sanitized Release Image (Dump from Stick & Clean)")
    if device.id == "custom":
        print("      Dumps raw eMMC from device, extracts calibration to calibration/,")
        print("      cleans sensitive data, and packages dist/openstick-custom-linux.zip.")
    else:
        print(f"      Dumps raw eMMC from device, extracts calibration to calibration/,")
        print(f"      cleans sensitive data, and packages dist/openstick-{device.id}-linux.zip.")
    print("  [4] Exit")
    print("-" * 65)

    while True:
        try:
            choice = input("Please select action [1-4] or 'q' to quit: ").strip().lower()
            if choice in ("1", "debian", "linux", "install"):
                return "linux"
            elif choice in ("2", "stock", "restore"):
                return "stock"
            elif choice in ("3", "dump", "release", "image", "clean"):
                return "release"
            elif choice in ("4", "3_legacy", "q", "quit", "exit"):
                return "exit"
            print("[-] Invalid selection. Enter 1, 2, 3, or 4.")
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(1)


def prompt_custom_image_path(dry_run: bool = False) -> Path:
    """
    Prompt user to provide the file path to their custom Linux raw eMMC image or zip package.
    Strips surrounding quotes and expands user paths (~).
    """
    print("\n" + "=" * 65)
    print("                CUSTOM LINUX IMAGE SPECIFICATION")
    print("=" * 65)
    print("Please specify the path to your custom raw eMMC image or firmware package.")
    print("Supported formats:")
    print("  - Raw disk image (.bin, .img) containing a valid GPT partition table")
    print("  - Firmware package (.zip) containing full_emmc.bin")
    print("=" * 65)

    while True:
        try:
            raw_input_path = input("\nEnter custom image path (or 'q' to cancel): ").strip()
            if raw_input_path.lower() in ("q", "quit", "cancel"):
                print("Aborted.")
                sys.exit(0)

            if not raw_input_path:
                print("[-] Path cannot be empty.")
                continue

            # Strip quotes (common when dragging and dropping files in terminal)
            cleaned = raw_input_path.strip("\"'")
            candidate = Path(cleaned).expanduser().resolve()

            if dry_run:
                print(f"[DRY-RUN] Selected custom image path: {candidate}")
                return candidate

            if not candidate.exists():
                print(f"[-] File not found: {candidate}")
                continue

            if candidate.is_file():
                return candidate
            elif candidate.is_dir():
                from openstick.releases import find_raw_image_in_dir
                raw_in_dir = find_raw_image_in_dir(candidate)
                if raw_in_dir:
                    print(f"[+] Found raw eMMC image: {raw_in_dir.name}")
                    return raw_in_dir
                print(f"[-] Path is a directory: {candidate}. Please specify a .bin, .img, or .zip file.")
                continue
            else:
                print(f"[-] Invalid file path: {candidate}")
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(1)


def show_post_install_info(
    mode: str,
    detected_ip: Optional[str] = None,
    detected_imei: Optional[str] = None,
    device_id: Optional[str] = None,
):
    """Display connection instructions after flashing completes."""
    print("\n" + "=" * 65)
    if mode == "linux":
        if detected_ip:
            print("          CONGRATULATIONS! DEBIAN LINUX IS READY")
            print("=" * 65)
            print(f"The stick is online and responding at: {detected_ip}")
            if detected_imei:
                print(f"Modem IMEI: {detected_imei}")
            print("")
            print("How to connect:")
            print("  1. USB Network Adapter (Active & Verified):")
            print(f"     - Stick IP: {detected_ip}")
            print(f"     - SSH:      ssh user@{detected_ip}")
            print("     - Password: 1")
            print("     - Root:     sudo su (passwordless)")
            print("\n  2. Wi-Fi Access Point (Fallback / Standalone):")
            print("     - SSID:     Openstick")
            print("     - Password: openstick")
            print("     - Stick IP: 192.168.4.1 (or 192.168.5.1)")
            print("     - SSH:      ssh user@192.168.4.1 (Password: 1)")
            print("\n  3. Test Hardware LEDs:")
            print("     - Command:  led-test (or 'led-test --help' for options)")
        else:
            print("          CONGRATULATIONS! DEBIAN LINUX IS NOW INSTALLED")
            print("=" * 65)
            print("The stick is rebooting into Debian Linux. Please allow 30-45 seconds")
            print("for the first boot to initialize system services.\n")
            print("How to connect:")
            print("  1. USB Network Adapter (CDC-ECM / RNDIS) [Recommended]:")
            print("     - Stick IP: 192.168.5.1 (or 192.168.68.1)")
            print("     - SSH:      ssh user@192.168.5.1")
            print("     - Password: 1")
            print("     - Root:     sudo su (passwordless)")
            print("\n  2. Wi-Fi Access Point (if enabled):")
            print("     - SSID:     Openstick")
            print("     - Password: openstick")
            print("     - Stick IP: 192.168.4.1 (or 192.168.5.1)")
            print("     - SSH:      ssh user@192.168.4.1 (Password: 1)")
            print("\n  3. Test Hardware LEDs:")
            print("     - Command:  led-test (or 'led-test --help' for options)")

        if device_id and device_id.lower() in ("hmmifib", "hm-mifib", "mifib", "mf800"):
            print("\n  4. HM-MIFIB Battery & LCD Utilities:")
            print("     - Battery:  battery (capacity %, voltage & charging status)")
            print("     - LCD Mode: lcd-show <status|glosos|wave|on|off> (or lcd_ctl)")
            print("     - Cellular: lte (SIM status, signal strength & IP)")
            print("     - USB Role: usb-mode <status|gadget|host>")
    else:
        print("          STOCK FACTORY FIRMWARE RESTORED")
        print("=" * 65)
        print("The stick has been restored from your full eMMC backup and is rebooting.")
        print("  - Default Wi-Fi SSID is printed on the stick casing.")
        print("  - Web GUI: http://192.168.100.1 (Login: admin)")

    print("=" * 65 + "\n")
