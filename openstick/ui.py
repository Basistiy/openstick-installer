"""User Interface helpers and menu presentation for OpenStick Installer."""

import sys
from pathlib import Path
from typing import Dict, List, Optional
from openstick.devices import DeviceModel, get_device_by_id


def print_banner():
    """Print welcoming ASCII banner."""
    banner = r"""
   ___                   ____  _   _      _    
  / _ \ _ __   ___ _ __ / ___|| |_(_) ___| | __
 | | | | '_ \ / _ \ '_ \\___ \| __| |/ __| |/ /
 | |_| | |_) |  __/ | | |___) | |_| | (__|   < 
  \___/| .__/ \___|_| |_|____/ \__|_|\___|_|\_\
       |_|  MSM8916 Linux Installer v0.1.0
=====================================================
"""
    print(banner)


def show_board_menu() -> Optional[DeviceModel]:
    """
    Display initial board selection menu:
      [1] UZ801
      [2] Other
    Returns DeviceModel for UZ801, or None if Other is selected.
    """
    print("\n[+] Step 1: Select your target board")
    print("-" * 55)
    print("  [1] UZ801 (4G LTE USB Modem Dongle — Qualcomm MSM8916)")
    print("  [2] Other board")
    print("-" * 55)

    while True:
        try:
            choice = input("Please select board [1-2] or 'q' to quit: ").strip().lower()
            if choice in ("q", "quit", "exit"):
                print("Exiting.")
                sys.exit(0)

            if choice in ("1", "uz801"):
                return get_device_by_id("uz801")
            elif choice in ("2", "other"):
                show_other_board_message()
                return None

            print("[-] Invalid selection. Enter 1 for UZ801 or 2 for Other.")
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(1)


def show_other_board_message():
    """Display GitHub issue guidance when user chooses 'Other board'."""
    print("\n" + "=" * 68)
    print("                     BOARD SUPPORT REQUEST")
    print("=" * 68)
    print("Currently, OpenStick Installer officially supports the UZ801 board.")
    print("We are actively expanding support for additional MSM8916 boards!\n")
    print("Please open a GitHub issue to request support for your board:")
    print("  👉 https://github.com/Basistiy/openstick-installer/issues\n")
    print("Helpful details to include in your issue:")
    print("  • Board name / model printed on the casing")
    print("  • PCB silk markings / revision (e.g. UZ801-V3, SP970, MF70, etc.)")
    print("  • High-resolution photos of both sides of the board")
    print("=" * 68 + "\n")


def show_device_info(device: DeviceModel):
    """Display summary and notes for the selected device."""
    print("\n" + "=" * 60)
    print(f" Selected Device: {device.name}")
    print("=" * 60)
    print(f"  • SoC:              {device.soc}")
    print(f"  • RAM / Storage:    {device.ram} / {device.storage}")
    print(f"  • Default Web UI:   {device.adb_enable_url}")
    print(f"  • Firehose Loader:  {device.recommended_loader}")
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
    print("\nSoftware Options (No opening casing / no button needed):")
    print("  • If stick is running Android:")
    print(f"    1. Connect PC to stick's Wi-Fi network.")
    print(f"    2. Open {device.adb_enable_url} in browser and toggle USB Debug ON.")
    print("    3. Plug stick into USB — installer will reboot it automatically.")
    print("  • If stick is running Linux (Debian):")
    print("    1. SSH to the stick:  ssh user@192.168.5.1  (Password: 1)")
    print("    2. Run command:       sudo systemctl reboot bootloader")
    print("    3. The installer will catch it in Fastboot and reboot into EDL mode.")
    print("  • If stick is in Fastboot mode:")
    print("    Run command:         fastboot oem reboot-edl")
    print("\nHardware Option (Recovery Button or EDL Pins):")
    print("  1. Unplug the stick from USB.")
    print("  2. Hold down the physical recovery button on the board,")
    print("     or short the two EDL test pins/pads with tweezers.")
    print("  3. While holding the button or shorting pins, plug into USB.")
    print("  4. Release the button / pins after 3 seconds.")
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
    print(f"  • Backup Directory:   {report.get('directory')}")
    print(f"  • Full eMMC Clone:    {report.get('image_file')} ({report.get('image_size_gb')} GB)")
    print(f"  • Total Partitions:   {report.get('gpt_partitions_count')}")
    if calibration_dir:
        print(f"  • Active Calibration: {calibration_dir.resolve()}")

    verified = report.get("verified_partitions", [])
    if verified:
        print("\n  Extracted Calibration Sidecars:")
        for part in verified:
            label = part.get("label", "")
            actual = format_size(part.get("actual_bytes", 0))
            print(f"    [✓] {label:<16} : {actual:>9}")

    missing = report.get("missing_critical", [])
    if missing:
        print(f"\n  [!] WARNING: Missing calibration partitions: {', '.join(missing)}")
    else:
        print("\n  [✓] All unique cellular calibration partitions successfully backed up!")

    print("*" * 65 + "\n")


def show_action_menu(device: DeviceModel) -> str:
    """Display interactive action menu."""
    print("\n[+] Step 3: Choose Next Action")
    print("-" * 65)
    print("  [1] Install Linux (Debian) [Recommended]")
    print(f"      Downloads universal Linux image for {device.name.split()[0]},")
    print("      injects your unique calibration partitions, and flashes via EDL.")
    print("  [2] Restore Stock Backup")
    print(f"      Flashes your original raw eMMC backup from backups/ to restore Android.")
    print("  [3] Create Sanitized Release Image (Dump from Stick & Clean)")
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


def show_post_install_info(mode: str, detected_ip: Optional[str] = None):
    """Display connection instructions after flashing completes."""
    print("\n" + "=" * 65)
    if mode == "linux":
        if detected_ip:
            print("          CONGRATULATIONS! DEBIAN LINUX IS READY")
            print("=" * 65)
            print(f"The stick is online and responding at: {detected_ip}\n")
            print("How to connect:")
            print("  1. USB Network Adapter (Active & Verified):")
            print(f"     • Stick IP: {detected_ip}")
            print(f"     • SSH:      ssh user@{detected_ip}")
            print("     • Password: 1")
            print("     • Root:     sudo su (passwordless)")
            print("\n  2. Wi-Fi Access Point (Fallback / Standalone):")
            print("     • SSID:     Openstick")
            print("     • Password: openstick")
            print("     • Stick IP: 192.168.4.1 (or 192.168.5.1)")
            print("     • SSH:      ssh user@192.168.4.1 (Password: 1)")
            print("\n  3. Test Hardware LEDs:")
            print("     • Command:  led-test (or 'led-test --help' for options)")
        else:
            print("          CONGRATULATIONS! DEBIAN LINUX IS NOW INSTALLED")
            print("=" * 65)
            print("The stick is rebooting into Debian Linux. Please allow 30-45 seconds")
            print("for the first boot to initialize system services.\n")
            print("How to connect:")
            print("  1. USB Network Adapter (CDC-ECM / RNDIS) [Recommended]:")
            print("     • Stick IP: 192.168.5.1 (or 192.168.68.1)")
            print("     • SSH:      ssh user@192.168.5.1")
            print("     • Password: 1")
            print("     • Root:     sudo su (passwordless)")
            print("\n  2. Wi-Fi Access Point (if enabled):")
            print("     • SSID:     Openstick")
            print("     • Password: openstick")
            print("     • Stick IP: 192.168.4.1 (or 192.168.5.1)")
            print("     • SSH:      ssh user@192.168.4.1 (Password: 1)")
            print("\n  3. Test Hardware LEDs:")
            print("     • Command:  led-test (or 'led-test --help' for options)")
    else:
        print("          STOCK FACTORY FIRMWARE RESTORED")
        print("=" * 65)
        print("The stick has been restored from your full eMMC backup and is rebooting.")
        print("  • Default Wi-Fi SSID is printed on the stick casing.")
        print("  • Web GUI: http://192.168.100.1 (Login: admin)")

    print("=" * 65 + "\n")
