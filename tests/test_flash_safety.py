"""Tests for the pre-flash size check and post-flash read-back verification."""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openstick.edl import (
    check_image_fits,
    create_synthetic_raw_image,
    flash_raw_emmc_via_edl,
    read_device_total_sectors,
    verify_flashed_image,
)

DEVICE_SECTORS = 8192
SMALL_LAYOUT = [("boot", 4900, 128), ("rootfs", 5100, 2000)]  # ends at 7099
LARGE_LAYOUT = [("boot", 4900, 128), ("rootfs", 5100, 3200)]  # ends at 8299, past the device


class FakeStick:
    """In-memory eMMC that serves 'edl rs' reads and 'edl wf' writes."""

    def __init__(self, sectors: int, gpt_source: Path, write_succeeds: bool = True):
        self.data = bytearray(sectors * 512)
        self.data[: 34 * 512] = gpt_source.read_bytes()[: 34 * 512]
        self.write_succeeds = write_succeeds
        self.calls = []

    def run_edl_command(self, args, loader=None, dry_run=False, timeout=1800):
        self.calls.append(args[0])
        if args[0] == "rs":
            start, count, out = int(args[1]), int(args[2]), Path(args[3])
            out.write_bytes(bytes(self.data[start * 512 : (start + count) * 512]))
            return True
        if args[0] == "wf":
            if self.write_succeeds:
                image = Path(args[1]).read_bytes()
                self.data[: len(image)] = image
            return True  # edl reports success either way (bkerler/edl#809)
        if args[0] == "reset":
            return True
        raise AssertionError(f"unexpected edl command {args}")


class TestFlashSafety(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.stock = self.test_dir / "stock.bin"
        create_synthetic_raw_image(self.stock, num_total_sectors=DEVICE_SECTORS, partitions=SMALL_LAYOUT)
        self.small = self.test_dir / "small.bin"
        create_synthetic_raw_image(self.small, num_total_sectors=DEVICE_SECTORS, partitions=SMALL_LAYOUT)
        self.large = self.test_dir / "large.bin"
        create_synthetic_raw_image(self.large, num_total_sectors=8300, partitions=LARGE_LAYOUT)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_check_image_fits_accepts_small_image(self):
        fits, _ = check_image_fits(self.small, DEVICE_SECTORS)
        self.assertTrue(fits)

    def test_check_image_fits_rejects_partition_past_end(self):
        # File (8300 sectors) fits, but rootfs ends at 8299, past the last usable sector 8276.
        fits, reason = check_image_fits(self.large, 8310)
        self.assertFalse(fits)
        self.assertIn("8299", reason)

    def test_check_image_fits_rejects_oversized_file(self):
        fits, reason = check_image_fits(self.large, DEVICE_SECTORS)
        self.assertFalse(fits)
        self.assertIn("8300", reason)

    def test_read_device_total_sectors_from_gpt(self):
        stick = FakeStick(DEVICE_SECTORS, self.stock)
        with patch("openstick.edl.run_edl_command", side_effect=stick.run_edl_command):
            self.assertEqual(read_device_total_sectors(), DEVICE_SECTORS)

    def test_read_device_total_sectors_without_gpt(self):
        stick = FakeStick(DEVICE_SECTORS, self.stock)
        stick.data[512:520] = b"\x00" * 8
        with patch("openstick.edl.run_edl_command", side_effect=stick.run_edl_command):
            self.assertIsNone(read_device_total_sectors())

    def test_flash_refuses_image_larger_than_stick(self):
        stick = FakeStick(DEVICE_SECTORS, self.stock)
        with patch("openstick.edl.run_edl_command", side_effect=stick.run_edl_command):
            ok = flash_raw_emmc_via_edl(self.large, inject_calibration=False)
        self.assertFalse(ok)
        self.assertNotIn("wf", stick.calls)

    def test_flash_uses_given_device_size(self):
        stick = FakeStick(DEVICE_SECTORS, self.stock)
        with patch("openstick.edl.run_edl_command", side_effect=stick.run_edl_command):
            ok = flash_raw_emmc_via_edl(self.large, inject_calibration=False, device_sectors=DEVICE_SECTORS)
        self.assertFalse(ok)
        self.assertNotIn("wf", stick.calls)

    def test_flash_detects_write_that_reported_success(self):
        stick = FakeStick(DEVICE_SECTORS, self.stock, write_succeeds=False)
        with patch("openstick.edl.run_edl_command", side_effect=stick.run_edl_command):
            ok = flash_raw_emmc_via_edl(self.small, inject_calibration=False)
        self.assertFalse(ok)
        self.assertIn("wf", stick.calls)
        self.assertNotIn("reset", stick.calls)

    def test_flash_verifies_and_resets_on_success(self):
        stick = FakeStick(DEVICE_SECTORS, self.stock)
        with patch("openstick.edl.run_edl_command", side_effect=stick.run_edl_command):
            ok = flash_raw_emmc_via_edl(self.small, inject_calibration=False)
        self.assertTrue(ok)
        self.assertEqual(stick.calls[-1], "reset")

    def test_verify_flashed_image_matches(self):
        stick = FakeStick(DEVICE_SECTORS, self.stock)
        stick.data[: self.small.stat().st_size] = self.small.read_bytes()
        with patch("openstick.edl.run_edl_command", side_effect=stick.run_edl_command):
            self.assertTrue(verify_flashed_image(self.small))

    def test_verify_flashed_image_catches_unwritten_tail(self):
        stick = FakeStick(DEVICE_SECTORS, self.stock)
        stick.data[: self.small.stat().st_size] = self.small.read_bytes()
        stick.data[7090 * 512 : 7100 * 512] = b"\x00" * (10 * 512)  # end of rootfs never written
        with patch("openstick.edl.run_edl_command", side_effect=stick.run_edl_command):
            self.assertFalse(verify_flashed_image(self.small))


if __name__ == "__main__":
    unittest.main()
