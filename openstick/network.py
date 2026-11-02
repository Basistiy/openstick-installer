"""
Network discovery and verification utilities for OpenStick Debian devices.
Locates connected sticks via USB Ethernet (CDC-ECM/RNDIS) and Wi-Fi,
and identifies active SSH endpoints with default credentials.
"""

import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from typing import List, Optional, Set, Tuple

DEFAULT_CANDIDATE_IPS = [
    "192.168.5.1",    # OpenStick Debian default USB CDC-ECM gateway
    "192.168.68.1",   # OpenStick Debian alternative RNDIS gateway
    "192.168.4.1",    # OpenStick Debian default Wi-Fi AP gateway
]

USB_GADGET_KEYWORDS = (
    "gadget",
    "rndis",
    "remote ndis",
    "cdc",
    "ncm",
    "openstick",
    "msm8916",
    "linux usb",
)

NON_OPENSTICK_BANNER_TOKENS = (
    "dropbear",
    "rosssh",
    "cisco",
    "ubuntu",
    "freebsd",
    "openbsd",
    "netbsd",
    "windows",
    "apple",
    "centos",
    "fedora",
    "redhat",
    "alpine",
    "arch",
    "synology",
    "qnap",
    "ubnt",
    "edgerouter",
    "unifi",
)

DEFAULT_SSH_USER = "user"
DEFAULT_SSH_PASSWORD = "1"
DEFAULT_SSH_PORT = 22


def _is_usb_gadget_port_name(name: str) -> bool:
    """Return True if an adapter or hardware port description looks like a USB gadget NIC."""
    if not name:
        return False
    lower = name.lower()
    return any(keyword in lower for keyword in USB_GADGET_KEYWORDS)


def _get_darwin_usb_gadget_ifaces(hw_ports_output: str) -> Set[str]:
    """Extract BSD interface names (e.g. 'en9') belonging to USB gadget adapters on macOS."""
    usb_ifaces: Set[str] = set()
    current_port = ""
    for raw_line in hw_ports_output.splitlines():
        line = raw_line.strip()
        if line.startswith("Hardware Port:"):
            current_port = line.split(":", 1)[1].strip()
        elif line.startswith("Device:"):
            dev = line.split(":", 1)[1].strip()
            if dev and _is_usb_gadget_port_name(current_port):
                usb_ifaces.add(dev)
    return usb_ifaces


def _is_linux_usb_net_iface(iface: str) -> bool:
    """Return True if a Linux network interface belongs to a USB Ethernet/RNDIS gadget."""
    if not iface:
        return False
    if iface.startswith(("usb", "rndis", "enx")) or re.match(r"^en[a-z0-9]*u\d+", iface):
        return True
    sysfs_dev = f"/sys/class/net/{iface}/device"
    if os.path.exists(sysfs_dev):
        try:
            if "usb" in os.path.realpath(sysfs_dev).lower():
                return True
        except OSError:
            pass
    return False


def _extract_windows_usb_gadget_gateways(ipconfig_all_output: str) -> List[str]:
    """Extract gateway IPs only from USB RNDIS/CDC/Gadget adapter blocks in 'ipconfig /all'."""
    gateways: List[str] = []
    sections: List[str] = []
    current_lines: List[str] = []

    for raw_line in ipconfig_all_output.splitlines():
        if raw_line and not raw_line[0].isspace() and raw_line.rstrip().endswith(":"):
            if current_lines:
                sections.append("\n".join(current_lines))
            current_lines = [raw_line]
        elif current_lines:
            current_lines.append(raw_line)
    if current_lines:
        sections.append("\n".join(current_lines))

    ignored_prefixes = ("127.", "0.", "255.", "169.254.")
    for section in sections:
        if not _is_usb_gadget_port_name(section):
            continue
        for prefix, host_octet in re.findall(r"\b(\d+\.\d+\.\d+)\.(\d+)\b", section):
            full_ip = f"{prefix}.{host_octet}"
            if full_ip.startswith(ignored_prefixes):
                continue
            gw_ip = full_ip if host_octet == "1" else f"{prefix}.1"
            if gw_ip not in gateways:
                gateways.append(gw_ip)

    return gateways


def get_candidate_ips() -> List[str]:
    """
    Retrieve candidate IP addresses for the OpenStick device,
    combining standard default subnets with dynamically discovered USB gadget gateways.
    Intentionally excludes regular Wi-Fi / LAN default gateways (e.g. home routers at 192.168.1.1).
    """
    candidates = list(DEFAULT_CANDIDATE_IPS)

    try:
        if sys.platform == "darwin":
            hw_out = subprocess.run(
                ["networksetup", "-listallhardwareports"],
                capture_output=True,
                text=True,
                timeout=3,
            ).stdout
            usb_ifaces = _get_darwin_usb_gadget_ifaces(hw_out)
            if usb_ifaces:
                out = subprocess.run(
                    ["netstat", "-rn", "-f", "inet"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                ).stdout
                for line in out.splitlines():
                    parts = line.split()
                    if len(parts) >= 4 and parts[3] in usb_ifaces:
                        dest, gw = parts[0], parts[1]
                        if dest == "default" and re.match(r"^\d+\.\d+\.\d+\.\d+$", gw):
                            if gw not in candidates:
                                candidates.append(gw)
                        elif re.match(r"^\d+\.\d+\.\d+$", dest):
                            subnet_gw = f"{dest}.1"
                            if subnet_gw not in candidates:
                                candidates.append(subnet_gw)
        elif sys.platform.startswith("linux"):
            try:
                out = subprocess.run(
                    ["ip", "-4", "route", "show"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                ).stdout
                for line in out.splitlines():
                    m_dev = re.search(r"\bdev\s+(\S+)", line)
                    if not m_dev or not _is_linux_usb_net_iface(m_dev.group(1)):
                        continue
                    for match in re.findall(r"\bvia\s+(\d+\.\d+\.\d+\.\d+)", line):
                        if match not in candidates:
                            candidates.append(match)
                    m_subnet = re.match(r"^\s*(\d+\.\d+\.\d+)\.\d+/\d+", line)
                    if m_subnet:
                        gw = f"{m_subnet.group(1)}.1"
                        if gw not in candidates:
                            candidates.append(gw)
            except Exception:
                try:
                    with open("/proc/net/route", "r") as f:
                        for line in f.readlines()[1:]:
                            fields = line.strip().split()
                            if len(fields) >= 3 and _is_linux_usb_net_iface(fields[0]):
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
                out_ipcfg = subprocess.run(
                    ["ipconfig", "/all"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                ).stdout
                for gw_ip in _extract_windows_usb_gadget_gateways(out_ipcfg):
                    if gw_ip not in candidates:
                        candidates.append(gw_ip)
            except Exception:
                pass
    except Exception:
        pass

    return candidates


def is_openstick_ssh_banner(banner: str) -> bool:
    """
    Validate whether an SSH identification string belongs to an OpenStick Debian installation.
    Rejects router/embedded SSH daemons (Dropbear, MikroTik ROSSH, Cisco) and non-Debian OSes.
    """
    if not banner:
        return False
    lower = banner.strip().lower()
    if "ssh-" not in lower or "openssh" not in lower:
        return False
    if any(token in lower for token in NON_OPENSTICK_BANNER_TOKENS):
        return False
    return True


def probe_ssh_endpoint(ip: str, port: int = DEFAULT_SSH_PORT, timeout: float = 0.8) -> Optional[str]:
    """
    Quickly probe a candidate IP on SSH port 22 and read the software identification banner.
    Returns the decoded banner string if an OpenStick-compatible OpenSSH service responds, or None.
    """
    try:
        with socket.create_connection((ip, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            raw = sock.recv(256)
            banner = raw.decode("utf-8", errors="ignore").strip()
            for line in banner.splitlines():
                clean_line = line.strip()
                if is_openstick_ssh_banner(clean_line):
                    return clean_line
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
        print("    [+] OpenStick detected at 192.168.5.1 (SSH-2.0-OpenSSH_10.0p2 Debian-7+deb13u4)")
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
    print("  - SSID:     Openstick")
    print("  - Password: openstick")
    print("  - Stick IP: 192.168.4.1")
    print(f"  - SSH:      ssh {DEFAULT_SSH_USER}@192.168.4.1 (Password: {DEFAULT_SSH_PASSWORD})")
    print("=" * 65 + "\n")


def _did_ssh_reboot_succeed(result: subprocess.CompletedProcess) -> bool:
    """
    Determine whether an SSH reboot invocation authenticated and executed.
    Note: 'sudo reboot' frequently drops the TCP connection mid-session (exit 255 with empty
    stderr under LogLevel=ERROR), whereas failed authentication or unreachable hosts report
    explicit error messages on stderr (or sshpass exit code 5).
    """
    if result.returncode == 5:  # sshpass: invalid/incorrect password
        return False
    stderr_text = result.stderr.lower() if isinstance(result.stderr, str) else ""
    failure_markers = (
        "permission denied",
        "authentication failed",
        "connection refused",
        "no route to host",
        "network is unreachable",
        "timed out",
        "could not resolve",
        "host key verification failed",
    )
    if any(marker in stderr_text for marker in failure_markers):
        return False
    return result.returncode in (0, 255)


def reboot_stick_to_bootloader(
    ip: str,
    user: str = DEFAULT_SSH_USER,
    password: str = DEFAULT_SSH_PASSWORD,
    port: int = DEFAULT_SSH_PORT,
    dry_run: bool = False,
) -> bool:
    """
    Issue a remote reboot command over SSH to restart an OpenStick running Linux
    into Bootloader / Fastboot mode (or directly EDL).
    Handles standard OpenStick Debian credentials ('user' / '1' with passwordless sudo).
    """
    if dry_run:
        print(f"[DRY-RUN] Simulating SSH command to {user}@{ip}: 'sudo systemctl reboot bootloader'...")
        return True

    ssh_bin = shutil.which("ssh")
    if not ssh_bin:
        return False

    # Command sequence to trigger reboot into bootloader / fastboot
    remote_cmd = (
        "sudo systemctl reboot bootloader 2>/dev/null "
        "|| sudo reboot bootloader 2>/dev/null "
        "|| sudo systemctl reboot edl 2>/dev/null "
        "|| sudo reboot edl 2>/dev/null "
        "|| sudo reboot 2>/dev/null"
    )

    ssh_opts = [
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=5",
        "-o", "LogLevel=ERROR",
        "-p", str(port),
    ]

    target = f"{user}@{ip}"

    # Method 1: sshpass if available
    sshpass_bin = shutil.which("sshpass")
    if sshpass_bin:
        try:
            res = subprocess.run(
                [sshpass_bin, "-p", password, ssh_bin] + ssh_opts + [target, remote_cmd],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if _did_ssh_reboot_succeed(res):
                return True
        except subprocess.TimeoutExpired:
            return True
        except Exception:
            pass

    # Method 2: SSH_ASKPASS on Unix (macOS / Linux)
    if sys.platform != "win32":
        askpass_script = None
        try:
            with tempfile.NamedTemporaryFile("w", delete=False) as f:
                f.write(f"#!/bin/sh\necho '{password}'\n")
                askpass_script = f.name
            os.chmod(askpass_script, 0o755)

            env = os.environ.copy()
            env["SSH_ASKPASS"] = askpass_script
            env["SSH_ASKPASS_REQUIRE"] = "force"
            env["DISPLAY"] = ":0"

            res = subprocess.run(
                [ssh_bin] + ssh_opts + [target, remote_cmd],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if _did_ssh_reboot_succeed(res):
                return True
        except subprocess.TimeoutExpired:
            return True
        except Exception:
            pass
        finally:
            if askpass_script and os.path.exists(askpass_script):
                try:
                    os.remove(askpass_script)
                except OSError:
                    pass

    # Method 3: Direct non-interactive SSH invocation (works if SSH keys or passwordless SSH is configured)
    try:
        res = subprocess.run(
            [ssh_bin, "-o", "BatchMode=yes"] + ssh_opts + [target, remote_cmd],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if _did_ssh_reboot_succeed(res):
            return True
    except subprocess.TimeoutExpired:
        return True
    except Exception:
        pass

    return False

