"""Tests for Qualcomm EDL engine, GPT parsing, sanitization, and calibration injection."""

import io
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from tests.fakes import FakeProcess

from openstick.edl import (
    is_edl_connected,
    wait_for_edl,
    find_edl_runner,
    run_edl_command,
    parse_gpt_from_raw_image,
    extract_partitions_from_raw_image,
    sanitize_raw_image,
    inject_partitions_into_raw_image,
    create_synthetic_raw_image,
    execute_raw_emmc_backup,
    verify_raw_backup,
    flash_raw_emmc_via_edl,
    has_valid_calibration,
    find_latest_valid_backup,
    clean_rootfs_sensitive_data,
    compress_raw_image_to_zip,
    find_debugfs,
    DEFAULT_CALIBRATION_PARTITIONS,
    ALL_CALIBRATION_PARTITIONS,
)


class TestEdl(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.synthetic_image = self.test_dir / "synthetic_emmc.bin"
        create_synthetic_raw_image(self.synthetic_image)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @patch("openstick.edl.detect_edl_via_pyusb", return_value=False)
    @patch("openstick.edl.detect_edl_via_serial", return_value=False)
    @patch("openstick.edl.detect_edl_via_system_profiler", return_value=False)
    @patch("openstick.edl.detect_edl_via_lsusb", return_value=False)
    def test_is_edl_connected_all_false(self, *mocks):
        self.assertFalse(is_edl_connected())

    @patch("openstick.edl.detect_edl_via_pyusb", return_value=True)
    def test_is_edl_connected_pyusb_true(self, mock_pyusb):
        self.assertTrue(is_edl_connected())

    def test_wait_for_edl_dry_run(self):
        self.assertTrue(wait_for_edl(timeout=2, dry_run=True))

    def test_parse_gpt_from_raw_image(self):
        gpt = parse_gpt_from_raw_image(self.synthetic_image)
        self.assertIn("__metadata__", gpt)
        self.assertEqual(gpt["__metadata__"]["current_lba"], 1)

        # Check expected partitions exist in GPT
        for p in ["fsc", "fsg", "modem", "modemst1", "modemst2", "persist", "sec", "boot", "rootfs"]:
            self.assertIn(p, gpt)
            self.assertGreater(gpt[p]["byte_size"], 0)
            self.assertEqual(gpt[p]["byte_offset"], gpt[p]["start_sector"] * 512)

    def test_extract_partitions_from_raw_image(self):
        extract_dir = self.test_dir / "extracted"
        ok = extract_partitions_from_raw_image(self.synthetic_image, extract_dir)
        self.assertTrue(ok)

        # Check extracted files
        for p in ALL_CALIBRATION_PARTITIONS:
            file_path = extract_dir / f"{p}.bin"
            self.assertTrue(file_path.exists())
            self.assertGreater(file_path.stat().st_size, 0)
            # Verify contents start with expected test tag
            data = file_path.read_bytes()
            self.assertTrue(data.startswith(f"PARTITION_{p.upper()}".encode("ascii")))

    def test_sanitize_and_inject_roundtrip(self):
        # 1. Read original calibration data
        extract_dir = self.test_dir / "original_calib"
        extract_partitions_from_raw_image(self.synthetic_image, extract_dir)

        # 2. Sanitize image in-place (zeros out unique calibration partitions)
        ok, summary = sanitize_raw_image(self.synthetic_image)
        self.assertTrue(ok)
        self.assertGreaterEqual(len(summary), len(DEFAULT_CALIBRATION_PARTITIONS))

        # Check that modemst1 is now all 0x00
        gpt = parse_gpt_from_raw_image(self.synthetic_image)
        with open(self.synthetic_image, "rb") as f:
            f.seek(gpt["modemst1"]["byte_offset"])
            wiped_bytes = f.read(gpt["modemst1"]["byte_size"])
            self.assertEqual(wiped_bytes, b"\x00" * gpt["modemst1"]["byte_size"])

            # Check that boot is untouched
            f.seek(gpt["boot"]["byte_offset"])
            boot_bytes = f.read(len(b"PARTITION_BOOT"))
            self.assertEqual(boot_bytes, b"PARTITION_BOOT")

        # 3. Inject calibration back in-place
        ok_inject, injected = inject_partitions_into_raw_image(
            self.synthetic_image,
            calibration_dir=extract_dir,
        )
        self.assertTrue(ok_inject)
        self.assertIn("modemst1", injected)
        self.assertIn("modemst2", injected)
        self.assertIn("fsg", injected)

        # 4. Verify modemst1 is restored to original content
        with open(self.synthetic_image, "rb") as f:
            f.seek(gpt["modemst1"]["byte_offset"])
            restored_bytes = f.read(gpt["modemst1"]["byte_size"])
            original_bytes = (extract_dir / "modemst1.bin").read_bytes()
            self.assertEqual(restored_bytes, original_bytes)

    def test_execute_raw_emmc_backup_dry_run(self):
        backup_dir = self.test_dir / "backup_dry"
        calib_dir = self.test_dir / "calib_dry"
        ok = execute_raw_emmc_backup(backup_dir, calibration_dir=calib_dir, dry_run=True)
        self.assertTrue(ok)
        self.assertTrue((backup_dir / "full_emmc.bin").exists())
        self.assertTrue((backup_dir / "calibration" / "modemst1.bin").exists())
        self.assertTrue((calib_dir / "modemst1.bin").exists())

    def test_verify_raw_backup(self):
        backup_dir = self.test_dir / "backup_verify"
        calib_dir = backup_dir / "calibration"
        calib_dir.mkdir(parents=True)

        create_synthetic_raw_image(backup_dir / "full_emmc.bin")
        for p in DEFAULT_CALIBRATION_PARTITIONS:
            (calib_dir / f"{p}.bin").write_bytes(b"\x01" * 1024)

        is_complete, report = verify_raw_backup(backup_dir)
        self.assertTrue(is_complete)
        self.assertEqual(len(report["missing_critical"]), 0)
        self.assertEqual(len(report["empty_partitions"]), 0)
        self.assertEqual(report["image_file"], "full_emmc.bin")

    def test_verify_raw_backup_missing_partition(self):
        backup_dir = self.test_dir / "backup_missing"
        calib_dir = backup_dir / "calibration"
        calib_dir.mkdir(parents=True)

        create_synthetic_raw_image(backup_dir / "full_emmc.bin")
        # Only modemst1
        (calib_dir / "modemst1.bin").write_bytes(b"\x01" * 1024)

        is_complete, report = verify_raw_backup(backup_dir)
        self.assertFalse(is_complete)
        self.assertIn("modemst2", report["missing_critical"])

    def test_has_valid_calibration(self):
        calib_dir = self.test_dir / "calib_check"
        self.assertFalse(has_valid_calibration(calib_dir))

        calib_dir.mkdir()
        for p in DEFAULT_CALIBRATION_PARTITIONS:
            (calib_dir / f"{p}.bin").write_bytes(b"\x01" * 512)

        self.assertTrue(has_valid_calibration(calib_dir))

        # Check supporting .img format
        (calib_dir / "modemst1.bin").unlink()
        (calib_dir / "modemst1.img").write_bytes(b"\x01" * 512)
        self.assertTrue(has_valid_calibration(calib_dir))

        # fsc is allowed to be all-zero on hardware
        (calib_dir / "fsc.bin").write_bytes(b"\x00" * 512)
        self.assertTrue(has_valid_calibration(calib_dir))

        # Zeroed-out modemst1 (sanitized) must be rejected
        (calib_dir / "modemst1.img").write_bytes(b"\x00" * 512)
        self.assertFalse(has_valid_calibration(calib_dir))

    def test_find_latest_valid_backup(self):
        backups_dir = self.test_dir / "backups"
        backups_dir.mkdir()

        # Old backup
        old_dir = backups_dir / "uz801_20261019_100000"
        old_dir.mkdir()
        (old_dir / "full_emmc.bin").write_bytes(b"\x01" * 1024)

        # New backup
        new_dir = backups_dir / "uz801_20261020_120000"
        new_dir.mkdir()
        (new_dir / "full_emmc.bin").write_bytes(b"\x01" * 1024)

        # Sanitized release dump directory must be ignored even though 'uz801_release_' sorts after 'uz801_2026'
        rel_dir = backups_dir / "uz801_release_20261021_120000"
        rel_dir.mkdir()
        (rel_dir / "full_emmc.bin").write_bytes(b"\x01" * 1024)

        found = find_latest_valid_backup(self.test_dir, "uz801")
        self.assertIsNotNone(found)
        self.assertEqual(found, new_dir)

    def test_find_latest_valid_backup_with_imei_suffix(self):
        backups_dir = self.test_dir / "backups"
        if not backups_dir.exists():
            backups_dir.mkdir()

        # Older backup without IMEI
        old_dir = backups_dir / "uz801_20261020_120000"
        old_dir.mkdir(exist_ok=True)
        (old_dir / "full_emmc.bin").write_bytes(b"\x01" * 1024)

        # Newer backup with IMEI suffix
        newer_dir = backups_dir / "uz801_20261022_150000_860123456789014"
        newer_dir.mkdir(exist_ok=True)
        (newer_dir / "full_emmc.bin").write_bytes(b"\x01" * 1024)

        found = find_latest_valid_backup(self.test_dir, "uz801")
        self.assertIsNotNone(found)
        self.assertEqual(found, newer_dir)

    def test_flash_raw_emmc_via_edl_dry_run(self):
        self.assertTrue(flash_raw_emmc_via_edl(self.synthetic_image, dry_run=True))

    @patch("openstick.edl.subprocess.Popen")
    @patch("openstick.edl.find_edl_runner", return_value=["edl"])
    def test_run_edl_command_memory_flag_handling(self, mock_runner, mock_popen):
        mock_popen.return_value = FakeProcess(stdout="Done")

        # Storage command 'wf' should include --memory=eMMC
        self.assertTrue(run_edl_command(["wf", "full_emmc.bin"]))
        wf_cmd = mock_popen.call_args_list[-1][0][0]
        self.assertIn("--memory=eMMC", wf_cmd)

        # Control command 'reset' must NOT include --memory=eMMC
        self.assertTrue(run_edl_command(["reset"]))
        reset_cmd = mock_popen.call_args_list[-1][0][0]
        self.assertNotIn("--memory=eMMC", reset_cmd)

    @patch("openstick.edl.subprocess.Popen")
    @patch("openstick.edl.find_edl_runner", return_value=["edl"])
    def test_run_edl_command_windows_driver_error_handling(self, mock_runner, mock_popen):
        mock_popen.return_value = FakeProcess(
            returncode=1,
            stderr="raise NotImplementedError(_strerror(ret))\nNotImplementedError: Operation not supported",
        )
        stderr = io.StringIO()
        with patch("sys.stderr", stderr):
            self.assertFalse(run_edl_command(["rf", "full_emmc.bin"]))

        self.assertIn("Zadig", stderr.getvalue())

    @patch("openstick.edl.subprocess.Popen")
    @patch("openstick.edl.find_edl_runner", return_value=["edl"])
    def test_run_edl_command_sahara_firehose_error_handling(self, mock_runner, mock_popen):
        mock_popen.return_value = FakeProcess(
            returncode=1,
            stdout="main - Device detected :)\nmain - Mode detected: error\nConnection detected, quiting.",
        )
        stderr = io.StringIO()
        with patch("sys.stderr", stderr):
            self.assertFalse(run_edl_command(["rf", "full_emmc.bin"]))

        self.assertIn("FIREHOSE", stderr.getvalue())

    @patch("openstick.edl.subprocess.Popen")
    @patch("openstick.edl.find_edl_runner", return_value=["edl"])
    def test_run_edl_command_sets_utf8_env(self, mock_runner, mock_popen):
        mock_popen.return_value = FakeProcess(stdout="Done")
        self.assertTrue(run_edl_command(["reset"]))
        env_passed = mock_popen.call_args[1]["env"]
        self.assertEqual(env_passed.get("PYTHONIOENCODING"), "utf-8")
        self.assertEqual(env_passed.get("PYTHONUTF8"), "1")

    def test_extract_partitions_truncated_image_rejected(self):
        # Truncate synthetic image to 20000 bytes (GPT header valid, but partitions extend past EOF)
        truncated_img = self.test_dir / "truncated.bin"
        truncated_img.write_bytes(self.synthetic_image.read_bytes()[:20000])
        out_dir = self.test_dir / "extracted_truncated"
        ok = extract_partitions_from_raw_image(truncated_img, out_dir)
        self.assertFalse(ok)

    def test_find_latest_valid_backup_truncated_image_ignored(self):
        backups_dir = self.test_dir / "backups"
        backups_dir.mkdir(exist_ok=True)
        # Directory with truncated image that has valid GPT but cut off before partitions
        truncated_dir = backups_dir / "uz801_20261101_100000"
        truncated_dir.mkdir(exist_ok=True)
        (truncated_dir / "full_emmc.bin").write_bytes(self.synthetic_image.read_bytes()[:20000])

        # Valid backup
        valid_dir = backups_dir / "uz801_20261020_100000"
        valid_dir.mkdir(exist_ok=True)
        shutil.copy2(self.synthetic_image, valid_dir / "full_emmc.bin")

        found = find_latest_valid_backup(self.test_dir, "uz801")
        self.assertEqual(found, valid_dir)

    def test_inject_partitions_skips_zero_size_and_blank(self):
        calib_dir = self.test_dir / "test_calib_blank"
        calib_dir.mkdir()
        (calib_dir / "fsg.bin").write_bytes(b"")  # 0 bytes
        (calib_dir / "persist.bin").write_bytes(b"\x00" * 1024)  # blank/all zeros
        (calib_dir / "modemst1.bin").write_bytes(b"\x12\x34" * 16)  # valid

        img_copy = self.test_dir / "test_inject.bin"
        shutil.copy2(self.synthetic_image, img_copy)

        ok, injected = inject_partitions_into_raw_image(img_copy, calib_dir)
        self.assertTrue(ok)
        self.assertIn("modemst1", injected)
        self.assertNotIn("fsg", injected)
        self.assertNotIn("persist", injected)


    def test_clean_rootfs_sensitive_data_dry_run(self):
        ok, items = clean_rootfs_sensitive_data(self.synthetic_image, dry_run=True)
        self.assertTrue(ok)
        self.assertGreater(len(items), 0)

    def test_compress_raw_image_to_zip_dry_run(self):
        out_zip = self.test_dir / "test_out.zip"
        ok, sha = compress_raw_image_to_zip(self.synthetic_image, out_zip, dry_run=True)
        self.assertTrue(ok)
        self.assertEqual(sha, "mocksha256")
        self.assertTrue(out_zip.exists())
        self.assertTrue(out_zip.with_suffix(".zip.sha256").exists())

    def test_find_debugfs(self):
        # Should return a Path or None depending on system, but must not crash
        p = find_debugfs()
        if p is not None:
            self.assertTrue(p.exists())


if __name__ == "__main__":
    unittest.main()
