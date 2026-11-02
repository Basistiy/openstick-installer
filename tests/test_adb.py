"""Tests for ADB device management and reboot commands."""

import unittest
from unittest.mock import patch, MagicMock

from openstick.adb import (
    AdbDevice,
    is_adb_available,
    get_adb_devices,
    prepare_root,
    reboot_to_edl,
    reboot_to_bootloader,
    wait_for_device,
    validate_imei,
    get_device_imei,
)


class TestAdb(unittest.TestCase):
    def test_adb_device_is_ready(self):
        dev_ready = AdbDevice(serial="12345", state="device")
        self.assertTrue(dev_ready.is_ready)

        dev_unauth = AdbDevice(serial="12345", state="unauthorized")
        self.assertFalse(dev_unauth.is_ready)

    @patch("openstick.adb.shutil.which")
    def test_is_adb_available(self, mock_which):
        mock_which.return_value = "/usr/bin/adb"
        self.assertTrue(is_adb_available())

        mock_which.return_value = None
        self.assertFalse(is_adb_available())

    @patch("openstick.adb.is_adb_available", return_value=True)
    @patch("openstick.adb.subprocess.run")
    def test_get_adb_devices(self, mock_run, _):
        mock_output = (
            "List of devices attached\n"
            "0123456789abcdef       device product:msm8916 model:UZ801 device:uz801\n"
            "fedcba9876543210       unauthorized\n"
        )
        mock_run.return_value = MagicMock(stdout=mock_output, returncode=0)

        devices = get_adb_devices()
        self.assertEqual(len(devices), 2)
        self.assertEqual(devices[0].serial, "0123456789abcdef")
        self.assertEqual(devices[0].state, "device")
        self.assertEqual(devices[0].model, "UZ801")
        self.assertTrue(devices[0].is_ready)
        self.assertEqual(devices[1].serial, "fedcba9876543210")
        self.assertFalse(devices[1].is_ready)

    def test_reboot_to_edl_dry_run(self):
        self.assertTrue(reboot_to_edl(dry_run=True))

    def test_reboot_to_bootloader_dry_run(self):
        self.assertTrue(reboot_to_bootloader(dry_run=True))

    @patch("openstick.adb.subprocess.run")
    def test_reboot_to_bootloader_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        self.assertTrue(reboot_to_bootloader(serial="test_serial"))
        mock_run.assert_called_once_with(
            ["adb", "-s", "test_serial", "reboot", "bootloader"],
            capture_output=True,
            text=True,
            timeout=10,
        )

    @patch("openstick.adb.get_adb_devices")
    def test_wait_for_device_found(self, mock_get):
        mock_dev = AdbDevice(serial="test_serial", state="device")
        mock_get.return_value = [mock_dev]

        res = wait_for_device(timeout=1)
        self.assertIsNotNone(res)
        self.assertEqual(res.serial, "test_serial")

    @patch("openstick.adb.get_adb_devices")
    def test_wait_for_device_filters_by_serial(self, mock_get):
        other_dev = AdbDevice(serial="other_serial", state="device")
        target_dev = AdbDevice(serial="target_serial", state="device")
        mock_get.return_value = [other_dev, target_dev]

        res = wait_for_device(timeout=1, serial="target_serial")
        self.assertIsNotNone(res)
        self.assertEqual(res.serial, "target_serial")

    @patch("openstick.adb.subprocess.run")
    def test_prepare_root_already_root_skips_restart(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="uid=0(root) gid=0(root)\n")

        self.assertTrue(prepare_root(serial="uz801_serial"))
        mock_run.assert_called_once_with(
            ["adb", "-s", "uz801_serial", "shell", "id"],
            capture_output=True,
            text=True,
            timeout=4,
        )

    @patch("openstick.adb.wait_for_device")
    @patch("openstick.adb.subprocess.run")
    def test_prepare_root_restarts_adbd_and_waits_for_reenumeration(self, mock_run, mock_wait):
        mock_wait.return_value = AdbDevice(serial="hmuf_serial", state="device")
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="uid=2000(shell) gid=2000(shell)\n", stderr=""),
            MagicMock(returncode=0, stdout="restarting adbd as root\n", stderr=""),
            MagicMock(returncode=0, stdout="uid=0(root) gid=0(root)\n", stderr=""),
        ]

        self.assertTrue(prepare_root(serial="hmuf_serial"))
        mock_wait.assert_called_once_with(timeout=8, serial="hmuf_serial")
        self.assertEqual(mock_run.call_count, 3)

    def test_validate_imei(self):
        # Valid 15-digit Luhn IMEI
        self.assertTrue(validate_imei("860123456789014"))
        self.assertTrue(validate_imei("867530901234565"))
        # Valid 14-digit IMEI (without check digit)
        self.assertTrue(validate_imei("86012345678901"))

        # Invalid cases
        self.assertFalse(validate_imei("860123456789015"))  # Failed Luhn
        self.assertFalse(validate_imei("000000000000000"))  # Uniform digits
        self.assertFalse(validate_imei("111111111111111"))  # Uniform digits
        self.assertFalse(validate_imei("86012345678901A"))  # Non-digit
        self.assertFalse(validate_imei("12345"))            # Too short
        self.assertFalse(validate_imei("1234567890123456")) # Too long (16)
        self.assertFalse(validate_imei(None))
        self.assertFalse(validate_imei(""))

    def test_get_device_imei_dry_run(self):
        imei = get_device_imei(dry_run=True)
        self.assertEqual(imei, "860123456789014")
        self.assertTrue(validate_imei(imei))

    @patch("openstick.adb.subprocess.run")
    def test_get_device_imei_from_getprop(self, mock_run):
        def fake_run(cmd, **kwargs):
            if "getprop persist.radio.imei" in " ".join(cmd):
                return MagicMock(returncode=0, stdout="860123456789014\n")
            return MagicMock(returncode=0, stdout="\n")
        mock_run.side_effect = fake_run

        imei = get_device_imei(serial="serial123")
        self.assertEqual(imei, "860123456789014")

    @patch("openstick.adb.subprocess.run")
    def test_get_device_imei_from_dumpsys(self, mock_run):
        def fake_run(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "getprop" in cmd_str:
                return MagicMock(returncode=0, stdout="\n")
            if "dumpsys iphonesubinfo" in cmd_str:
                output = "Phone Subscriber Info:\n  Phone Type = GSM\n  Device ID = 867530901234565\n"
                return MagicMock(returncode=0, stdout=output)
            return MagicMock(returncode=0, stdout="")
        mock_run.side_effect = fake_run

        imei = get_device_imei(serial="serial123")
        self.assertEqual(imei, "867530901234565")

    @patch("openstick.adb.subprocess.run")
    def test_get_device_imei_from_at_smd_without_timeout(self, mock_run):
        executed_cmds = []

        def fake_run(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            executed_cmds.append(cmd_str)
            if "getprop" in cmd_str or "dumpsys" in cmd_str or "service call" in cmd_str:
                return MagicMock(returncode=0, stdout="\n")
            if "[ -e /dev/smd11 ]" in cmd_str:
                return MagicMock(returncode=0, stdout="yes\n")
            if "AT+CGSN" in cmd_str:
                return MagicMock(returncode=0, stdout="AT+CGSN\r\n867530901234565\r\n\r\nOK\r\n")
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = fake_run

        imei = get_device_imei(serial="hmuf_serial")
        self.assertEqual(imei, "867530901234565")
        at_invocations = [c for c in executed_cmds if "AT+CGSN" in c]
        self.assertEqual(len(at_invocations), 1)
        self.assertNotIn("timeout ", at_invocations[0])

    @patch("openstick.adb.subprocess.run")
    def test_get_device_imei_not_found(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        self.assertIsNone(get_device_imei(serial="serial123"))


if __name__ == "__main__":
    unittest.main()
