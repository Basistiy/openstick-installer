"""Integration tests for main CLI workflows."""

import io
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from main import main, handle_sanitize_image, ensure_device_in_edl
from openstick.devices import get_device_by_id
from openstick.fastboot import FastbootDevice
from openstick.adb import AdbDevice
from openstick.edl import create_synthetic_raw_image, parse_gpt_from_raw_image


class TestMain(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_sanitize_image_cli(self):
        image_path = self.test_dir / "full_emmc.bin"
        create_synthetic_raw_image(image_path)

        # Run sanitizer handler
        success = handle_sanitize_image(str(image_path))
        self.assertTrue(success)

        # Verify partitions were sanitized
        gpt = parse_gpt_from_raw_image(image_path)
        with open(image_path, "rb") as f:
            f.seek(gpt["modemst1"]["byte_offset"])
            self.assertEqual(f.read(gpt["modemst1"]["byte_size"]), b"\x00" * gpt["modemst1"]["byte_size"])

    @patch("sys.argv", ["main.py", "--find", "--dry-run"])
    def test_main_find_dry_run(self):
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            main()
        output = captured.getvalue()
        self.assertIn("OPENSTICK DEVICE DETECTED & VERIFIED", output)
        self.assertIn("192.168.5.1", output)

    @patch("sys.argv", ["main.py", "--board", "uz801", "--dry-run"])
    @patch("builtins.input", side_effect=["y", "1"])
    def test_main_board_flow_dry_run(self, mock_input):
        captured = io.StringIO()
        with patch("main.PROJECT_ROOT", self.test_dir), patch("sys.stdout", captured):
            main()
        output = captured.getvalue()
        self.assertIn("UZ801 (4G LTE USB Modem Dongle)", output)
        self.assertIn("BACKUP VERIFICATION SUMMARY", output)
        self.assertIn("INSTALLING OPENSTICK LINUX", output)


    @patch("sys.argv", ["main.py", "--board", "uz801", "--create-release", "--dry-run"])
    def test_main_create_release_dry_run(self):
        captured = io.StringIO()
        with patch("main.PROJECT_ROOT", self.test_dir), patch("sys.stdout", captured):
            with self.assertRaises(SystemExit) as cm:
                main()
        self.assertEqual(cm.exception.code, 0)
        output = captured.getvalue()
        self.assertIn("CREATING SANITIZED RELEASE IMAGE", output)
        self.assertIn("RELEASE IMAGE GENERATION COMPLETED SUCCESSFULLY", output)

    @patch("openstick.edl.is_edl_connected", return_value=False)
    @patch("openstick.fastboot.get_fastboot_devices")
    @patch("openstick.fastboot.reboot_to_edl", return_value=True)
    @patch("openstick.edl.wait_for_edl", return_value=True)
    def test_ensure_device_in_edl_via_fastboot(self, mock_wait_edl, mock_fb_reboot, mock_get_fb, _):
        mock_get_fb.return_value = [FastbootDevice(serial="162ad01f", state="fastboot")]
        device = get_device_by_id("uz801")
        self.assertTrue(ensure_device_in_edl(device, dry_run=False))
        mock_fb_reboot.assert_called_once_with("162ad01f", dry_run=False)

    @patch("openstick.edl.is_edl_connected", return_value=False)
    @patch("openstick.fastboot.get_fastboot_devices", return_value=[])
    @patch("openstick.adb.get_adb_devices")
    @patch("openstick.adb.prepare_root")
    @patch("openstick.adb.reboot_to_edl")
    @patch("openstick.fastboot.wait_for_device")
    @patch("openstick.fastboot.reboot_to_edl", return_value=True)
    @patch("openstick.edl.wait_for_edl", side_effect=[False, True])
    def test_ensure_device_in_edl_via_adb_fastboot_chain(
        self, mock_wait_edl, mock_fb_reboot, mock_wait_fb, mock_adb_reboot, mock_root, mock_adb_devs, mock_fb_devs, mock_is_edl
    ):
        mock_adb_devs.return_value = [AdbDevice(serial="adb_serial", state="device")]
        mock_wait_fb.return_value = FastbootDevice(serial="fb_serial", state="fastboot")
        device = get_device_by_id("uz801")
        self.assertTrue(ensure_device_in_edl(device, dry_run=False))
        mock_adb_reboot.assert_called_once()
        mock_fb_reboot.assert_called_once_with("fb_serial", dry_run=False)

    @patch("openstick.edl.is_edl_connected", return_value=False)
    @patch("openstick.fastboot.get_fastboot_devices", return_value=[])
    @patch("openstick.adb.get_adb_devices", return_value=[])
    @patch("openstick.network.find_stick_device")
    @patch("openstick.network.reboot_stick_to_bootloader", return_value=True)
    @patch("openstick.fastboot.wait_for_device")
    @patch("openstick.fastboot.reboot_to_edl", return_value=True)
    @patch("openstick.edl.wait_for_edl", return_value=True)
    def test_ensure_device_in_edl_via_linux_ssh(
        self, mock_wait_edl, mock_fb_reboot, mock_wait_fb, mock_ssh_reboot, mock_find, mock_adb_devs, mock_fb_devs, mock_is_edl
    ):
        mock_find.return_value = ("192.168.5.1", "SSH-2.0-OpenSSH")
        mock_wait_fb.return_value = FastbootDevice(serial="fb_from_ssh", state="fastboot")
        device = get_device_by_id("uz801")
        self.assertTrue(ensure_device_in_edl(device, dry_run=False))
        mock_ssh_reboot.assert_called_once_with("192.168.5.1", dry_run=False)
        mock_fb_reboot.assert_called_once_with("fb_from_ssh", dry_run=False)


if __name__ == "__main__":
    unittest.main()
