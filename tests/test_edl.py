"""Tests for Qualcomm EDL engine, GPT parsing, sanitization, and calibration injection."""

import io
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openstick.edl import (
    is_edl_connected,
    wait_for_edl,
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
    SSH_HOST_KEY_FILES,
)
from tests.fakes import FakeProcess, write_valid_dump


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

        old_dir = backups_dir / "uz801_20261019_100000"
        write_valid_dump(old_dir / "full_emmc.bin")

        new_dir = backups_dir / "uz801_20261020_120000"
        write_valid_dump(new_dir / "full_emmc.bin")

        # A sanitized release dump must be ignored even though 'uz801_release_' sorts after 'uz801_2026'
        rel_dir = backups_dir / "uz801_release_20261021_120000"
        write_valid_dump(rel_dir / "full_emmc.bin")

        found = find_latest_valid_backup(self.test_dir, "uz801")
        self.assertEqual(found, new_dir)

    def test_find_latest_valid_backup_with_imei_suffix(self):
        backups_dir = self.test_dir / "backups"
        backups_dir.mkdir()

        write_valid_dump(backups_dir / "uz801_20261020_120000" / "full_emmc.bin")
        newer_dir = backups_dir / "uz801_20261022_150000_860123456789014"
        write_valid_dump(newer_dir / "full_emmc.bin")

        self.assertEqual(find_latest_valid_backup(self.test_dir, "uz801"), newer_dir)

    def test_flash_raw_emmc_via_edl_dry_run(self):
        calib_dir = self.test_dir / "calib_dry"
        self.assertTrue(flash_raw_emmc_via_edl(self.synthetic_image, calibration_dir=calib_dir, dry_run=True))

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

    def test_clean_rootfs_sensitive_data_dry_run(self):
        ok, items = clean_rootfs_sensitive_data(self.synthetic_image, dry_run=True)
        self.assertTrue(ok)
        self.assertGreater(len(items), 0)
        self.assertIn("(dry-run) ssh-check-hostkeys.service injected", items)

    @patch("openstick.edl.subprocess.run")
    @patch("openstick.edl.find_debugfs", return_value=Path("/usr/sbin/debugfs"))
    def test_clean_rootfs_sensitive_data_removes_ssh_host_keys_and_injects_service(
        self, mock_find_debugfs, mock_run
    ):
        # Write ext4 superblock magic (0xef53) at rootfs offset + 1080
        gpt = parse_gpt_from_raw_image(self.synthetic_image)
        rootfs_offset = gpt["rootfs"]["byte_offset"]
        with open(self.synthetic_image, "r+b") as f:
            f.seek(rootfs_offset + 1080)
            f.write(b"\x53\xef")

        class DummyCompleted:
            def __init__(self, stdout=""):
                self.returncode = 0
                self.stdout = stdout
                self.stderr = ""

        def side_effect(cmd, **kwargs):
            if "-R" in cmd and "ls -p /etc/ssh" in cmd:
                return DummyCompleted(
                    "/1395/100600/0/0/ssh_host_custom_key/411/\n"
                    "/1403/100644/0/0/sshd_config/3424/\n"
                )
            return DummyCompleted()

        mock_run.side_effect = side_effect

        ok, cleaned = clean_rootfs_sensitive_data(self.synthetic_image, dry_run=False)
        self.assertTrue(ok)
        for key_path in SSH_HOST_KEY_FILES:
            self.assertIn(key_path, cleaned)
        self.assertIn("/etc/ssh/ssh_host_custom_key", cleaned)
        self.assertNotIn("/etc/ssh/sshd_config", cleaned)
        self.assertIn("/etc/systemd/system/ssh-check-hostkeys.service (injected)", cleaned)

        write_calls = [
            call for call in mock_run.call_args_list if "-w" in call[0][0]
        ]
        self.assertGreaterEqual(len(write_calls), 2)
        rm_input = write_calls[0][1]["input"]
        for key_path in SSH_HOST_KEY_FILES:
            self.assertIn(f"rm {key_path}", rm_input)
        self.assertIn("rm /etc/ssh/ssh_host_custom_key", rm_input)

        service_input = write_calls[1][1]["input"]
        self.assertIn("write ", service_input)
        self.assertIn("/etc/systemd/system/ssh-check-hostkeys.service", service_input)
        self.assertIn(
            "symlink /etc/systemd/system/ssh.service.wants/ssh-check-hostkeys.service /etc/systemd/system/ssh-check-hostkeys.service",
            service_input,
        )
        self.assertIn(
            "symlink /etc/systemd/system/sshd.service.wants/ssh-check-hostkeys.service /etc/systemd/system/ssh-check-hostkeys.service",
            service_input,
        )

    def test_clean_rootfs_sensitive_data_real_ext4(self):
        import subprocess

        debugfs_bin = find_debugfs()
        if not debugfs_bin:
            self.skipTest("debugfs not available")
        mke2fs_bin = debugfs_bin.parent / "mke2fs"
        if not mke2fs_bin.is_file():
            self.skipTest("mke2fs not available")

        img_path = self.test_dir / "real_ext4_emmc.bin"
        partitions = [
            ("boot", 40, 64),
            ("rootfs", 200, 8192),  # 4 MiB ext4 partition
        ]
        create_synthetic_raw_image(img_path, partitions=partitions)
        gpt = parse_gpt_from_raw_image(img_path)
        rootfs_offset = gpt["rootfs"]["byte_offset"]
        rootfs_size = gpt["rootfs"]["byte_size"]

        ext4_slice = self.test_dir / "rootfs.ext4"
        ext4_slice.write_bytes(b"\x00" * rootfs_size)
        subprocess.run([str(mke2fs_bin), "-F", str(ext4_slice)], capture_output=True, check=True)

        dummy_key = self.test_dir / "dummy_key"
        dummy_key.write_text("PRIVATE_KEY_DATA\n", encoding="utf-8")
        dummy_cfg = self.test_dir / "sshd_config"
        dummy_cfg.write_text("Port 22\n", encoding="utf-8")

        seed_cmds = [
            "mkdir /etc",
            "mkdir /etc/ssh",
            f"write {dummy_key} /etc/ssh/ssh_host_ed25519_key",
            f"write {dummy_key} /etc/ssh/ssh_host_ed25519_key.pub",
            f"write {dummy_cfg} /etc/ssh/sshd_config",
        ]
        subprocess.run(
            [str(debugfs_bin), "-w", str(ext4_slice)],
            input="\n".join(seed_cmds) + "\n",
            capture_output=True,
            text=True,
            check=True,
        )

        with open(img_path, "r+b") as f:
            f.seek(rootfs_offset)
            f.write(ext4_slice.read_bytes())

        ok, cleaned = clean_rootfs_sensitive_data(img_path, inject_led_test=False)
        self.assertTrue(ok)
        self.assertIn("/etc/ssh/ssh_host_ed25519_key", cleaned)
        self.assertIn("/etc/systemd/system/ssh-check-hostkeys.service (injected)", cleaned)

        target = f"{img_path}?offset={rootfs_offset}"
        ls_ssh = subprocess.run(
            [str(debugfs_bin), "-R", "ls -p /etc/ssh", target],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertNotIn("ssh_host_ed25519_key", ls_ssh.stdout)
        self.assertIn("sshd_config", ls_ssh.stdout)

        cat_unit = subprocess.run(
            [str(debugfs_bin), "-R", "cat /etc/systemd/system/ssh-check-hostkeys.service", target],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("ExecStart=/usr/bin/ssh-keygen -A", cat_unit.stdout)
        self.assertIn("ConditionPathExists=|!/etc/ssh/ssh_host_ed25519_key", cat_unit.stdout)

        stat_link = subprocess.run(
            [str(debugfs_bin), "-R", "stat /etc/systemd/system/ssh.service.wants/ssh-check-hostkeys.service", target],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("Type: symlink", stat_link.stdout)
        self.assertIn("/etc/systemd/system/ssh-check-hostkeys.service", stat_link.stdout)

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
