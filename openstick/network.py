"""
Network discovery and verification utilities for OpenStick Debian devices.
Locates connected sticks via USB Ethernet (CDC-ECM/RNDIS) and Wi-Fi,
and identifies active SSH endpoints with default credentials.
"""

import re
import socket
import subprocess
import sys
import time
from typing import List, Optional, Tuple

DEFAULT_CANDIDATE_IPS = [
    "192.168.5.1",    # OpenStick Debian default USB CDC-ECM gateway
    "192.168.68.1",   # OpenStick Debian alternative RNDIS gateway
    "192.168.4.1",    # OpenStick Debian default Wi-Fi AP gateway
    "192.168.100.1",  # Stock firmware Web GUI / fallback gateway
]

DEFAULT_SSH_USER = "user"
DEFAULT_SSH_PASSWORD = "1"
DEFAULT_SSH_PORT = 22


def get_candidate_ips() -> List[str]:
    """
    Retrieve candidate IP addresses for the OpenStick device,
    combining standard default subnets with dynamically discovered host gateways.
    """
    candidates = list(DEFAULT_CANDIDATE_IPS)

    try:
        if sys.platform == "darwin":
            out = subprocess.run(
                ["netstat", "-rn", "-f", "inet"],
                capture_output=True,
                text=True,
                timeout=3,
            ).stdout
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0] == "default":
                    gw = parts[1]
                    if re.match(r"^\d+\.\d+\.\d+\.\d+$", gw) and gw not in candidates:
                        candidates.append(gw)
        elif sys.platform.startswith("linux"):
            try:
                out = subprocess.run(
                    ["ip", "-4", "route", "show"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                ).stdout
                for match in re.findall(r"via\s+(\d+\.\d+\.\d+\.\d+)", out):
                    if match not in candidates:
                        candidates.append(match)
                for subnet in re.findall(r"(\d+\.\d+\.\d+)\.0/\d+\s+dev\s+(?:usb|en|eth)", out):
                    gw = f"{subnet}.1"
                    if gw not in candidates:
                        candidates.append(gw)
            except Exception:
                try:
                    with open("/proc/net/route", "r") as f:
                        for line in f.readlines()[1:]:
                            fields = line.strip().split()
                            if len(fields) >= 3:
                                gw_hex = fields[2]
                                if gw_hex != "00000000":
                                    octets = [str(int(gw_hex[i:i+2], 16)) for i in (6, 4, 2, 0)]
                                    gw_ip = ".".join(octets)
                                    if gw_ip not in candidates:
                                        candidates.append(gw_ip)
                except Exception:
                    pass
        elif sys.platform == "win32":
            try:
                out_route = subprocess.run(
                    ["route", "print", "-4"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                ).stdout
                for match in re.findall(r"0\.0\.0\.0\s+0\.0\.0\.0\s+(\d+\.\d+\.\d+\.\d+)", out_route):
                    if match not in candidates and not match.startswith("127."):
                        candidates.append(match)
            except Exception:
                pass

            try:
                out_ipcfg = subprocess.run(
                    ["ipconfig"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                ).stdout
                for match in re.findall(r"\b(192\.168\.\d+\.1)\b", out_ipcfg):
                    if match not in candidates:
                        candidates.append(match)
                for match in re.findall(r"(\d+\.\d+\.\d+\.\d+)", out_ipcfg):
                    if match.endswith(".1") and match not in candidates and not match.startswith("127."):
                        candidates.append(match)
            except Exception:
                pass
    except Exception:
        pass

    return candidates


def probe_ssh_endpoint(ip: str, port: int = DEFAULT_SSH_PORT, timeout: float = 0.8) -> Optional[str]:
    """
    Quickly probe a candidate IP on SSH port 22 and read the software identification banner.
    Returns the decoded banner string if an SSH service responds, or None.
    """
    try:
        with socket.create_connection((ip, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            raw = sock.recv(256)
            banner = raw.decode("utf-8", errors="ignore").strip()
            if "SSH" in banner:
                return banner
    except Exception:
        return None
    return None


def find_stick_device(dry_run: bool = False, timeout: float = 0.8) -> Optional[Tuple[str, str]]:
    """
    Scan candidate IP addresses to locate a responsive OpenStick device running SSH.
    Returns a tuple of (ip, banner) if found, or None.
    """
    if dry_run:
        print("[DRY-RUN] Simulating OpenStick device discovery...")
        return ("192.168.5.1", "SSH-2.0-OpenSSH_10.0p2 Debian-7+deb13u4")

    for ip in get_candidate_ips():
        banner = probe_ssh_endpoint(ip, timeout=timeout)
        if banner:
            return (ip, banner)

    return None


def wait_for_debian_boot(timeout: int = 60, dry_run: bool = False) -> Optional[str]:
    """
    Poll network interfaces until the device boots into Debian Linux and responds on SSH.
    Displays continuous progress feedback.
    """
    if dry_run:
        print("\n[*] [DRY-RUN] Simulating post-flash Debian Linux boot detection...")
        print("    [✓] OpenStick detected at 192.168.5.1 (SSH-2.0-OpenSSH_10.0p2 Debian-7+deb13u4)")
        return "192.168.5.1"

    print("\n[*] Waiting for stick to initialize Debian Linux (monitoring network & SSH)...", end="", flush=True)
    start_time = time.time()
    time.sleep(2)

    while time.time() - start_time < timeout:
        result = find_stick_device(dry_run=False, timeout=0.8)
        if result:
            ip, banner = result
            print(f"\n[+] OpenStick detected and responding at {ip}!")
            return ip

        time.sleep(2)
        sys.stdout.write(".")
        sys.stdout.flush()

    print("\n[!] Device is taking longer to initialize or USB Ethernet adapter is still connecting.")
    return None


def print_discovery_summary(ip: Optional[str] = None, banner: Optional[str] = None):
    """Print an interactive connection card with verified device details."""
    target_ip = ip or "192.168.5.1"
    status_label = "[+] OPENSTICK DEVICE DETECTED & VERIFIED" if ip else "[!] DEFAULT CONNECTION DETAILS"

    print("\n" + "=" * 65)
    print(f"       {status_label}")
    print("=" * 65)
    if banner:
        print(f"Service:     {banner}")
    print(f"Device IP:   {target_ip}")
    print(f"Username:    {DEFAULT_SSH_USER}")
    print(f"Password:    {DEFAULT_SSH_PASSWORD}")
    print(f"SSH Command: ssh {DEFAULT_SSH_USER}@{target_ip}")
    print(f"Root Access: sudo su (passwordless)")
    print("\nWi-Fi AP Fallback:")
    print("  • SSID:     Openstick")
    print("  • Password: openstick")
    print("  • Stick IP: 192.168.4.1")
    print(f"  • SSH:      ssh {DEFAULT_SSH_USER}@192.168.4.1 (Password: {DEFAULT_SSH_PASSWORD})")
    print("=" * 65 + "\n")
