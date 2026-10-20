"""Tests for ADB device management and reboot commands."""

import unittest
from unittest.mock import patch, MagicMock

from openstick.adb import (
    AdbDevice,
    is_adb_available,
    get_adb_devices,
    prepare_root,
    reboot_to_edl,
    wait_for_device,
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

    @patch("openstick.adb.get_adb_devices")
    def test_wait_for_device_found(self, mock_get):
        mock_dev = AdbDevice(serial="test_serial", state="device")
        mock_get.return_value = [mock_dev]

        res = wait_for_device(timeout=1)
        self.assertIsNotNone(res)
        self.assertEqual(res.serial, "test_serial")


if __name__ == "__main__":
    unittest.main()
