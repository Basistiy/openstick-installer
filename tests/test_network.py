"""Tests for network discovery and SSH verification."""

import io
import unittest
from unittest.mock import patch, MagicMock

from openstick.network import (
    get_candidate_ips,
    find_stick_device,
    is_openstick_ssh_banner,
    probe_ssh_endpoint,
    wait_for_debian_boot,
    reboot_stick_to_bootloader,
    parse_imei_from_output,
    get_stick_imei,
    ensure_stick_led_test,
    print_discovery_summary,
    DEFAULT_CANDIDATE_IPS,
)


class TestNetwork(unittest.TestCase):
    def test_get_candidate_ips_includes_defaults(self):
        candidates = get_candidate_ips()
        for ip in DEFAULT_CANDIDATE_IPS:
            self.assertIn(ip, candidates)

    def test_is_openstick_ssh_banner(self):
        self.assertTrue(is_openstick_ssh_banner("SSH-2.0-OpenSSH_10.0p2 Debian-7+deb13u4"))
        self.assertTrue(is_openstick_ssh_banner("SSH-2.0-OpenSSH_9.2p1"))
        self.assertFalse(is_openstick_ssh_banner("SSH-2.0-dropbear_2020.81"))
        self.assertFalse(is_openstick_ssh_banner("SSH-2.0-ROSSSH"))
        self.assertFalse(is_openstick_ssh_banner("SSH-2.0-Cisco-1.25"))
        self.assertFalse(is_openstick_ssh_banner("SSH-2.0-OpenSSH_9.6p1 Ubuntu-3ubuntu13"))
        self.assertFalse(is_openstick_ssh_banner("SSH-2.0-OpenSSH_9.8 FreeBSD-20240806"))
        self.assertFalse(is_openstick_ssh_banner(""))

    @patch("openstick.network.socket.create_connection")
    def test_probe_ssh_endpoint_rejects_dropbear_router(self, mock_conn):
        mock_sock = MagicMock()
        mock_sock.recv.return_value = b"SSH-2.0-dropbear_2020.81\r\n"
        mock_conn.return_value.__enter__.return_value = mock_sock

        self.assertIsNone(probe_ssh_endpoint("192.168.1.1"))

    @patch("openstick.network.socket.create_connection")
    def test_probe_ssh_endpoint_accepts_debian_openssh(self, mock_conn):
        mock_sock = MagicMock()
        mock_sock.recv.return_value = b"SSH-2.0-OpenSSH_10.0p2 Debian-7+deb13u4\r\n"
        mock_conn.return_value.__enter__.return_value = mock_sock

        self.assertEqual(
            probe_ssh_endpoint("192.168.5.1"),
            "SSH-2.0-OpenSSH_10.0p2 Debian-7+deb13u4",
        )

    @patch("openstick.network.sys.platform", "darwin")
    @patch("openstick.network.subprocess.run")
    def test_get_candidate_ips_darwin_excludes_wifi_router_includes_usb_gadget(self, mock_run):
        hw_ports = (
            "Hardware Port: Wi-Fi\n"
            "Device: en0\n"
            "Ethernet Address: fc:b2:14:72:67:4a\n\n"
            "Hardware Port: Bar Gadget\n"
            "Device: en9\n"
            "Ethernet Address: 2a:85:da:41:eb:f9\n"
        )
        netstat_out = (
            "Routing tables\n\n"
            "Internet:\n"
            "Destination        Gateway            Flags               Netif Expire\n"
            "default            192.168.1.1        UGScg                 en0\n"
            "default            192.168.7.1        UGScIg                en9\n"
        )
        mock_run.side_effect = [
            MagicMock(stdout=hw_ports),
            MagicMock(stdout=netstat_out),
        ]

        candidates = get_candidate_ips()
        self.assertNotIn("192.168.1.1", candidates)
        self.assertIn("192.168.7.1", candidates)

    @patch("openstick.network.sys.platform", "linux")
    @patch("openstick.network.subprocess.run")
    def test_get_candidate_ips_linux_excludes_wlan_includes_usb(self, mock_run):
        ip_route_out = (
            "default via 192.168.1.1 dev wlan0 proto dhcp metric 600\n"
            "192.168.1.0/24 dev wlan0 proto kernel scope link src 192.168.1.119\n"
            "default via 192.168.7.1 dev usb0 proto dhcp metric 100\n"
            "192.168.8.0/24 dev enx2a85da41ebf9 proto kernel scope link src 192.168.8.10\n"
        )
        mock_run.return_value = MagicMock(stdout=ip_route_out)

        candidates = get_candidate_ips()
        self.assertNotIn("192.168.1.1", candidates)
        self.assertIn("192.168.7.1", candidates)
        self.assertIn("192.168.8.1", candidates)

    @patch("openstick.network.sys.platform", "win32")
    @patch("openstick.network.subprocess.run")
    def test_get_candidate_ips_windows_excludes_wifi_includes_rndis(self, mock_run):
        ipconfig_all = (
            "Wireless LAN adapter Wi-Fi:\n\n"
            "   Description . . . . . . . . . . . : Intel(R) Wi-Fi 6 AX201\n"
            "   IPv4 Address. . . . . . . . . . . : 192.168.1.119(Preferred)\n"
            "   Default Gateway . . . . . . . . . : 192.168.1.1\n\n"
            "Ethernet adapter Ethernet 3:\n\n"
            "   Description . . . . . . . . . . . : Remote NDIS based Internet Sharing Device\n"
            "   IPv4 Address. . . . . . . . . . . : 192.168.7.242(Preferred)\n"
            "   Subnet Mask . . . . . . . . . . . : 255.255.255.0\n"
            "   Default Gateway . . . . . . . . . : 192.168.7.1\n"
        )
        mock_run.return_value = MagicMock(stdout=ipconfig_all)

        candidates = get_candidate_ips()
        self.assertNotIn("192.168.1.1", candidates)
        self.assertIn("192.168.7.1", candidates)

    def test_find_stick_device_dry_run(self):
        res = find_stick_device(dry_run=True)
        self.assertIsNotNone(res)
        ip, banner = res
        self.assertEqual(ip, "192.168.5.1")
        self.assertIn("SSH", banner)

    def test_wait_for_debian_boot_dry_run(self):
        ip = wait_for_debian_boot(timeout=2, dry_run=True)
        self.assertEqual(ip, "192.168.5.1")

    def test_reboot_stick_to_bootloader_dry_run(self):
        self.assertTrue(reboot_stick_to_bootloader("192.168.5.1", dry_run=True))

    @patch("openstick.network.shutil.which")
    @patch("openstick.network.subprocess.run")
    def test_reboot_stick_to_bootloader_ssh(self, mock_run, mock_which):
        def fake_which(cmd):
            if cmd == "ssh":
                return "/usr/bin/ssh"
            return None
        mock_which.side_effect = fake_which
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        self.assertTrue(reboot_stick_to_bootloader("192.168.5.1"))
        self.assertTrue(mock_run.called)

    @patch("openstick.network.shutil.which")
    @patch("openstick.network.subprocess.run")
    def test_reboot_stick_to_bootloader_auth_failure_returns_false(self, mock_run, mock_which):
        def fake_which(cmd):
            if cmd == "ssh":
                return "/usr/bin/ssh"
            return None
        mock_which.side_effect = fake_which
        mock_run.return_value = MagicMock(
            returncode=255,
            stderr="user@192.168.1.1: Permission denied (publickey,password).\n",
        )

        self.assertFalse(reboot_stick_to_bootloader("192.168.1.1"))

    def test_parse_imei_from_output(self):
        mmcli_kv = (
            "modem.dbus-path                       : /org/freedesktop/ModemManager1/Modem/0\n"
            "modem.generic.equipment-identifier    : 867530901234565\n"
            "modem.generic.state                   : enabled\n"
        )
        self.assertEqual(parse_imei_from_output(mmcli_kv), "867530901234565")

        mmcli_human = (
            "  --------------------------------\n"
            "  Hardware |   manufacturer: QUALCOMM INCORPORATED\n"
            "           |   equipment id: 860123456789014\n"
        )
        self.assertEqual(parse_imei_from_output(mmcli_human), "860123456789014")

        qmicli_out = "[/dev/wwan0qmi0] Device IDs retrieved:\n\tIMEI: '867530901234565'\n"
        self.assertEqual(parse_imei_from_output(qmicli_out), "867530901234565")

        at_out = "AT+CGSN\r\n860123456789014\r\n\r\nOK\r\n"
        self.assertEqual(parse_imei_from_output(at_out), "860123456789014")

        # Reject invalid Luhn or uniform dummy values
        self.assertIsNone(parse_imei_from_output("modem.generic.equipment-identifier : 000000000000000"))
        self.assertIsNone(parse_imei_from_output("modem.generic.equipment-identifier : 860123456789015"))
        self.assertIsNone(parse_imei_from_output(""))

    def test_get_stick_imei_dry_run(self):
        self.assertEqual(get_stick_imei("192.168.5.1", dry_run=True), "860123456789014")

    @patch("openstick.network.shutil.which")
    @patch("openstick.network.subprocess.run")
    def test_get_stick_imei_via_ssh(self, mock_run, mock_which):
        def fake_which(cmd):
            if cmd == "ssh":
                return "/usr/bin/ssh"
            return None

        mock_which.side_effect = fake_which
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="modem.generic.equipment-identifier : 867530901234565\n",
            stderr="",
        )

        imei = get_stick_imei("192.168.5.1", wait_seconds=4)
        self.assertEqual(imei, "867530901234565")
        self.assertTrue(mock_run.called)

    def test_print_discovery_summary_includes_imei(self):
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            print_discovery_summary(
                ip="192.168.5.1",
                banner="SSH-2.0-OpenSSH_10.0p2 Debian-7+deb13u4",
                imei="867530901234565",
            )
        output = captured.getvalue()
        self.assertIn("Modem IMEI:  867530901234565", output)

    def test_ensure_stick_led_test_dry_run(self):
        self.assertTrue(ensure_stick_led_test("192.168.5.1", dry_run=True))

    @patch("openstick.network.run_ssh_command")
    def test_ensure_stick_led_test_already_exists(self, mock_ssh):
        mock_ssh.return_value = (True, "ALREADY_EXISTS\n", "")
        self.assertTrue(ensure_stick_led_test("192.168.5.1"))
        self.assertTrue(mock_ssh.called)

    @patch("openstick.network.run_ssh_command")
    def test_ensure_stick_led_test_installs_successfully(self, mock_ssh):
        mock_ssh.return_value = (True, "INSTALLED\n", "")
        self.assertTrue(ensure_stick_led_test("192.168.5.1"))
        self.assertTrue(mock_ssh.called)


if __name__ == "__main__":
    unittest.main()
