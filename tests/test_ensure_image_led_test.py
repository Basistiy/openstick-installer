"""Unit tests for ensure_image_led_test script."""

import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from scripts.ensure_image_led_test import ensure_image_zip_has_led_test


class TestEnsureImageLedTest(unittest.TestCase):
    """Test suite for offline release image led-test injection."""

    def test_dry_run(self):
        res = ensure_image_zip_has_led_test(Path("dummy.zip"), dry_run=True)
        self.assertTrue(res)

    def test_missing_file_returns_false(self):
        res = ensure_image_zip_has_led_test(Path("/nonexistent/file.zip"), dry_run=False)
        self.assertFalse(res)

    @patch("scripts.ensure_image_led_test.find_debugfs")
    def test_no_debugfs_returns_false(self, mock_debugfs):
        mock_debugfs.return_value = None
        # Mock file exists
        with patch.object(Path, "exists", return_value=True):
            res = ensure_image_zip_has_led_test(Path("test.zip"), dry_run=False)
            self.assertFalse(res)


if __name__ == "__main__":
    unittest.main()
