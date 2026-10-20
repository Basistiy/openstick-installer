"""Integration tests for main CLI workflows."""

import io
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from main import main, handle_sanitize_image
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
        with patch("sys.stdout", captured):
            main()
        output = captured.getvalue()
        self.assertIn("UZ801 (4G LTE USB Modem Dongle)", output)
        self.assertIn("BACKUP VERIFICATION SUMMARY", output)
        self.assertIn("INSTALLING OPENSTICK LINUX", output)


if __name__ == "__main__":
    unittest.main()
