"""Tests for Fastboot device management and reboot commands."""

import unittest
from unittest.mock import patch, MagicMock

from openstick.fastboot import (
    FastbootDevice,
    is_fastboot_available,
    get_fastboot_devices,
    wait_for_device,
    reboot_to_edl,
    reboot_bootloader,
)


class TestFastboot(unittest.TestCase):
    @patch("openstick.fastboot.shutil.which")
    def test_is_fastboot_available(self, mock_which):
        mock_which.return_value = "/usr/bin/fastboot"
        self.assertTrue(is_fastboot_available())

        mock_which.return_value = None
        self.assertFalse(is_fastboot_available())

    @patch("openstick.fastboot.is_fastboot_available", return_value=True)
    @patch("openstick.fastboot.subprocess.run")
    def test_get_fastboot_devices(self, mock_run, _):
        mock_run.return_value = MagicMock(
            stdout="162ad01f\tfastboot\n87654321\tfastboot\n",
            returncode=0,
        )
        devices = get_fastboot_devices()
        self.assertEqual(len(devices), 2)
        self.assertEqual(devices[0].serial, "162ad01f")
        self.assertEqual(devices[0].state, "fastboot")
        self.assertEqual(devices[1].serial, "87654321")

    @patch("openstick.fastboot.get_fastboot_devices")
    def test_wait_for_device_found(self, mock_get):
        mock_get.return_value = [FastbootDevice(serial="162ad01f", state="fastboot")]
        dev = wait_for_device(timeout=1)
        self.assertIsNotNone(dev)
        self.assertEqual(dev.serial, "162ad01f")

    @patch("openstick.fastboot.get_fastboot_devices", return_value=[])
    def test_wait_for_device_timeout(self, _):
        dev = wait_for_device(timeout=1)
        self.assertIsNone(dev)

    def test_reboot_to_edl_dry_run(self):
        self.assertTrue(reboot_to_edl(serial="162ad01f", dry_run=True))

    @patch("openstick.fastboot.subprocess.run")
    def test_reboot_to_edl_oem_reboot_edl_success(self, mock_run):
        # Simulates: fastboot oem reboot-edl -> OKAY
        mock_run.return_value = MagicMock(stdout="OKAY [  0.003s]\nFinished.", stderr="", returncode=0)
        self.assertTrue(reboot_to_edl(serial="162ad01f"))
        mock_run.assert_called_once_with(
            ["fastboot", "-s", "162ad01f", "oem", "reboot-edl"],
            capture_output=True,
            text=True,
            timeout=10,
        )

    @patch("openstick.fastboot.subprocess.run")
    def test_reboot_to_edl_fallback(self, mock_run):
        # 1st fails with unknown command, 2nd succeeds
        res_fail = MagicMock(stdout="", stderr="FAILED (remote: 'unknown command')", returncode=1)
        res_ok = MagicMock(stdout="OKAY [  0.002s]", stderr="", returncode=0)
        mock_run.side_effect = [res_fail, res_ok]

        self.assertTrue(reboot_to_edl())
        self.assertEqual(mock_run.call_count, 2)

    @patch("openstick.fastboot.subprocess.run")
    def test_reboot_to_edl_all_fail(self, mock_run):
        res_fail = MagicMock(stdout="", stderr="unknown command", returncode=1)
        mock_run.return_value = res_fail
        self.assertFalse(reboot_to_edl())

    def test_reboot_bootloader_dry_run(self):
        self.assertTrue(reboot_bootloader(dry_run=True))

    @patch("openstick.fastboot.subprocess.run")
    def test_reboot_bootloader_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        self.assertTrue(reboot_bootloader(serial="162ad01f"))
        mock_run.assert_called_once_with(
            ["fastboot", "-s", "162ad01f", "reboot", "bootloader"],
            capture_output=True,
            text=True,
            timeout=10,
        )


if __name__ == "__main__":
    unittest.main()
