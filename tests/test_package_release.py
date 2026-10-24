"""Unit tests for package_release script."""

import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.package_release import (
    build_release_packages,
    collect_release_files,
    compute_sha256,
    get_version,
    validate_release_manifest,
)


class TestPackageRelease(unittest.TestCase):
    """Test suite for release packaging logic and safety checks."""

    def setUp(self):
        self.repo_root = Path(__file__).resolve().parent.parent

    def test_get_version(self):
        ver = get_version(self.repo_root)
        self.assertTrue(ver.startswith("v"))
        self.assertIn(".", ver)

    def test_collect_release_files(self):
        files = collect_release_files(self.repo_root)
        self.assertIn("run.bat", files)
        self.assertIn("run.command", files)
        self.assertIn("run.sh", files)
        self.assertIn("main.py", files)
        self.assertIn("requirements.txt", files)
        self.assertIn("openstick/__init__.py", files)
        self.assertIn("openstick/bootstrap.py", files)

        # Ensure permissions
        self.assertTrue(files["run.command"][1])  # executable
        self.assertTrue(files["run.sh"][1])       # executable
        self.assertFalse(files["run.bat"][1])     # non-executable

    def test_validate_release_manifest_clean(self):
        files = collect_release_files(self.repo_root)
        self.assertTrue(validate_release_manifest(files))

    def test_validate_release_manifest_catches_leak(self):
        files = {
            "calibration/modemst1.bin": (Path("dummy.bin"), False)
        }
        with self.assertRaises(ValueError):
            validate_release_manifest(files)

        files = {
            "backups/uz801_dump/full_emmc.bin": (Path("dummy.bin"), False)
        }
        with self.assertRaises(ValueError):
            validate_release_manifest(files)

    def test_build_release_packages(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            latest_zip, versioned_zip, sha256_file = build_release_packages(
                self.repo_root, out_dir, "v0.1.0"
            )

            self.assertTrue(latest_zip.is_file())
            self.assertTrue(versioned_zip.is_file())
            self.assertTrue(sha256_file.is_file())

            # Verify contents of generated zip
            with zipfile.ZipFile(latest_zip, "r") as zf:
                namelist = zf.namelist()
                self.assertIn("run.bat", namelist)
                self.assertIn("run.command", namelist)
                self.assertIn("run.sh", namelist)
                self.assertIn("main.py", namelist)
                self.assertIn("backups/", namelist)
                self.assertIn("calibration/", namelist)

                # Check executable attributes on run.sh and run.command
                info_sh = zf.getinfo("run.sh")
                mode = info_sh.external_attr >> 16
                self.assertTrue(mode & 0o111)

                info_cmd = zf.getinfo("run.command")
                mode = info_cmd.external_attr >> 16
                self.assertTrue(mode & 0o111)

            # Check checksums file
            content = sha256_file.read_text()
            self.assertIn("openstick-installer.zip", content)
            self.assertIn("openstick-installer-v0.1.0.zip", content)


if __name__ == "__main__":
    unittest.main()
