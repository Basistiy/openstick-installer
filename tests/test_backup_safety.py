"""A failed or truncated dump must never feed calibration reuse or flashing."""

import io
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main as main_module
from openstick.edl import (
    execute_raw_emmc_backup,
    extract_partitions_from_raw_image,
    find_latest_valid_backup,
    flash_raw_emmc_via_edl,
    inject_partitions_into_raw_image,
)
from tests.fakes import write_valid_dump


class TestBackupFailClosed(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.backup = self.root / "backups" / "uz801_20261118_120000"
        self.calibration = self.root / "calibration"

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _write_dump(self, path: Path, truncated: bool = False) -> None:
        write_valid_dump(path)
        if truncated:
            # Cut off persist/sec/boot/rootfs while keeping a parseable GPT.
            path.write_bytes(path.read_bytes()[: 4600 * 512])

    def test_failed_edl_dump_discards_partial_files(self):
        def fake_edl(args, **kwargs):
            self.backup.mkdir(parents=True, exist_ok=True)
            (self.backup / "full_emmc.bin").write_bytes(b"partial dump")
            return False

        with patch("openstick.edl.run_edl_command", side_effect=fake_edl), patch("sys.stderr", io.StringIO()):
            ok = execute_raw_emmc_backup(self.backup, calibration_dir=self.calibration)

        self.assertFalse(ok)
        self.assertFalse((self.backup / "full_emmc.bin").exists())

    def test_truncated_dump_is_rejected_before_sidecar_extraction(self):
        def fake_edl(args, **kwargs):
            self._write_dump(self.backup / "full_emmc.bin", truncated=True)
            return True

        with patch("openstick.edl.run_edl_command", side_effect=fake_edl), patch("sys.stderr", io.StringIO()):
            ok = execute_raw_emmc_backup(self.backup, calibration_dir=self.calibration)

        self.assertFalse(ok)
        self.assertFalse((self.backup / "full_emmc.bin").exists())
        self.assertFalse((self.backup / "calibration").exists())
        self.assertFalse(self.calibration.exists())

    def test_complete_dump_extracts_valid_sidecars(self):
        def fake_edl(args, **kwargs):
            self._write_dump(self.backup / "full_emmc.bin")
            return True

        with patch("openstick.edl.run_edl_command", side_effect=fake_edl):
            ok = execute_raw_emmc_backup(self.backup, calibration_dir=self.calibration)

        self.assertTrue(ok)
        for name in ("fsc", "fsg", "modemst1", "modemst2", "persist", "sec"):
            self.assertTrue((self.backup / "calibration" / f"{name}.bin").is_file())
            self.assertTrue((self.calibration / f"{name}.bin").is_file())

    def test_extraction_refuses_truncated_image_without_writing_sidecars(self):
        image = self.root / "truncated.bin"
        self._write_dump(image, truncated=True)
        out = self.root / "sidecars"

        with patch("sys.stderr", io.StringIO()):
            ok = extract_partitions_from_raw_image(image, out)

        self.assertFalse(ok)
        self.assertFalse(out.exists())

    def test_find_latest_valid_backup_skips_truncated_dump(self):
        bad = self.root / "backups" / "uz801_20261117_120000"
        bad.mkdir(parents=True)
        self._write_dump(bad / "full_emmc.bin", truncated=True)

        good = self.root / "backups" / "uz801_20261118_120000"
        good.mkdir(parents=True)
        self._write_dump(good / "full_emmc.bin")

        self.assertEqual(find_latest_valid_backup(self.root, "uz801"), good)

    def test_blank_calibration_sidecar_aborts_injection(self):
        image = self.root / "image.bin"
        write_valid_dump(image)
        calib = self.root / "calib"
        extract_partitions_from_raw_image(image, calib)
        original = image.read_bytes()

        for blank in (b"", b"\x00" * 1024):
            (calib / "fsg.bin").write_bytes(blank)
            with patch("sys.stderr", io.StringIO()):
                ok, injected = inject_partitions_into_raw_image(image, calib)

            self.assertFalse(ok)
            self.assertEqual(injected, [])
            self.assertEqual(image.read_bytes(), original)

    def test_flash_refuses_when_calibration_is_incomplete(self):
        image = self.root / "image.bin"
        device_sectors = write_valid_dump(image)
        self.calibration.mkdir(parents=True)
        extract_partitions_from_raw_image(image, self.calibration)
        (self.calibration / "fsg.bin").write_bytes(b"")

        with patch("openstick.edl.run_edl_command") as mock_edl, patch("sys.stderr", io.StringIO()):
            ok = flash_raw_emmc_via_edl(
                image,
                calibration_dir=self.calibration,
                device_sectors=device_sectors,
            )

        self.assertFalse(ok)
        mock_edl.assert_not_called()

    @patch("sys.argv", ["main.py", "--board", "uz801", "--skip-bootstrap"])
    def test_main_aborts_when_backup_fails(self):
        with patch("main.PROJECT_ROOT", self.root), \
             patch("main.prompt_backup_partitions", return_value=True), \
             patch("main.handle_partition_backup", return_value=(False, None)), \
             patch("main.show_action_menu") as mock_menu, \
             patch("sys.stdout", io.StringIO()), \
             patch("sys.stderr", io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                main_module.main()

        self.assertEqual(cm.exception.code, 1)
        mock_menu.assert_not_called()


if __name__ == "__main__":
    unittest.main()
