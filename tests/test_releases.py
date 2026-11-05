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
    extract_local_release_zip,
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
                {"name": "openstick-installer.zip", "browser_download_url": "https://..."},
                {"name": "openstick-uz801-linux.zip", "browser_download_url": "https://..."},
                {"name": "openstick-hmuf02-linux.zip", "browser_download_url": "https://..."},
                {"name": "openstick-hmmifib-linux.zip", "browser_download_url": "https://..."},
                {"name": "openstick-uz801-stock-recovery.zip", "browser_download_url": "https://..."},
            ]
        }
        uz_asset = find_matching_asset(release, "uz801", mode="linux")
        self.assertIsNotNone(uz_asset)
        self.assertEqual(uz_asset["name"], "openstick-uz801-linux.zip")

        hmuf_asset = find_matching_asset(release, "hmuf02", mode="linux")
        self.assertIsNotNone(hmuf_asset)
        self.assertEqual(hmuf_asset["name"], "openstick-hmuf02-linux.zip")

        mifib_asset = find_matching_asset(release, "hmmifib", mode="linux")
        self.assertIsNotNone(mifib_asset)
        self.assertEqual(mifib_asset["name"], "openstick-hmmifib-linux.zip")

        mifib_alias_asset = find_matching_asset(
            {"assets": [{"name": "openstick-hm-mifib-linux.zip", "browser_download_url": "https://..."}]},
            "hmmifib",
            mode="linux",
        )
        self.assertIsNotNone(mifib_alias_asset)
        self.assertEqual(mifib_alias_asset["name"], "openstick-hm-mifib-linux.zip")

    def test_find_matching_asset_does_not_cross_match_other_board_or_installer(self):
        release = {
            "assets": [
                {"name": "openstick-installer.zip", "browser_download_url": "https://..."},
                {"name": "openstick-uz801-linux.zip", "browser_download_url": "https://..."},
            ]
        }
        self.assertIsNone(find_matching_asset(release, "hmuf02", mode="linux"))

    def test_extract_local_release_zip(self):
        import zipfile
        raw_src = self.test_dir / "src_emmc.bin"
        create_synthetic_raw_image(raw_src)
        local_zip = self.test_dir / "openstick-hmuf02-linux.zip"
        with zipfile.ZipFile(local_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(raw_src, arcname="full_emmc.bin")

        ok, extracted = extract_local_release_zip(local_zip, self.test_dir)
        self.assertTrue(ok)
        self.assertIsNotNone(extracted)
        self.assertTrue((extracted / "full_emmc.bin").is_file())

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
