"""Tests for GitHub Releases querying and asset downloading."""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from openstick.releases import (
    find_matching_asset,
    calculate_sha256,
    find_raw_image_in_dir,
    download_and_extract_asset,
)
from openstick.edl import create_synthetic_raw_image


class TestReleases(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_find_matching_asset_linux(self):
        release = {
            "assets": [
                {"name": "openstick-uz801-linux.zip", "browser_download_url": "https://..."},
                {"name": "openstick-uz801-stock-recovery.zip", "browser_download_url": "https://..."},
            ]
        }
        asset = find_matching_asset(release, "uz801", mode="linux")
        self.assertIsNotNone(asset)
        self.assertEqual(asset["name"], "openstick-uz801-linux.zip")

    def test_find_matching_asset_stock(self):
        release = {
            "assets": [
                {"name": "openstick-uz801-linux.zip", "browser_download_url": "https://..."},
                {"name": "openstick-uz801-stock-recovery.zip", "browser_download_url": "https://..."},
            ]
        }
        asset = find_matching_asset(release, "uz801", mode="stock")
        self.assertIsNotNone(asset)
        self.assertEqual(asset["name"], "openstick-uz801-stock-recovery.zip")

    def test_calculate_sha256(self):
        test_file = self.test_dir / "sample.bin"
        test_file.write_bytes(b"OpenStick Installer Test Content")
        digest = calculate_sha256(test_file)
        self.assertIsInstance(digest, str)
        self.assertEqual(len(digest), 64)

    def test_find_raw_image_in_dir(self):
        # Empty dir
        self.assertIsNone(find_raw_image_in_dir(self.test_dir))

        # Dir with raw image containing EFI PART
        raw_img = self.test_dir / "custom_image.bin"
        create_synthetic_raw_image(raw_img)

        found = find_raw_image_in_dir(self.test_dir)
        self.assertIsNotNone(found)
        self.assertEqual(found, raw_img)

    def test_download_and_extract_asset_dry_run(self):
        asset = {"name": "openstick-uz801-linux.zip", "size": 1024}
        ok, extracted = download_and_extract_asset(
            asset=asset,
            tag_name="v0.1.0",
            project_root=self.test_dir,
            mode="linux",
            dry_run=True,
        )
        self.assertTrue(ok)
        self.assertIsNotNone(extracted)
        self.assertTrue((extracted / "full_emmc.bin").exists())


if __name__ == "__main__":
    unittest.main()
