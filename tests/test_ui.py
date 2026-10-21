"""Tests for User Interface presentation and menu handlers."""

import io
import sys
import unittest
from unittest.mock import patch

from openstick.ui import (
    show_board_menu,
    format_size,
    show_action_menu,
    prompt_backup_partitions,
    show_other_board_message,
)
from openstick.devices import get_device_by_id


class TestUI(unittest.TestCase):
    @patch("builtins.input", return_value="1")
    def test_show_board_menu_select_uz801(self, _):
        dev = show_board_menu()
        self.assertIsNotNone(dev)
        self.assertEqual(dev.id, "uz801")

    @patch("builtins.input", return_value="2")
    def test_show_board_menu_select_other(self, _):
        # Capturing stdout to verify GitHub issue link is presented
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            dev = show_board_menu()

        self.assertIsNone(dev)
        output = captured.getvalue()
        self.assertIn("https://github.com/Basistiy/openstick-flasher/issues", output)
        self.assertIn("BOARD SUPPORT REQUEST", output)

    def test_format_size(self):
        self.assertEqual(format_size(500), "500 B")
        self.assertEqual(format_size(2048), "2.00 KB")
        self.assertEqual(format_size(10485760), "10.00 MB")
        self.assertEqual(format_size(1073741824), "1.00 GB")

    @patch("builtins.input", return_value="y")
    def test_prompt_backup_partitions_yes(self, _):
        self.assertTrue(prompt_backup_partitions())

    @patch("builtins.input", return_value="n")
    def test_prompt_backup_partitions_no(self, _):
        self.assertFalse(prompt_backup_partitions())

    @patch("builtins.input", return_value="1")
    def test_show_action_menu_linux(self, _):
        dev = get_device_by_id("uz801")
        self.assertEqual(show_action_menu(dev), "linux")

    @patch("builtins.input", return_value="2")
    def test_show_action_menu_stock(self, _):
        dev = get_device_by_id("uz801")
        self.assertEqual(show_action_menu(dev), "stock")

    @patch("builtins.input", return_value="3")
    def test_show_action_menu_release(self, _):
        dev = get_device_by_id("uz801")
        self.assertEqual(show_action_menu(dev), "release")

    @patch("builtins.input", return_value="4")
    def test_show_action_menu_exit(self, _):
        dev = get_device_by_id("uz801")
        self.assertEqual(show_action_menu(dev), "exit")


if __name__ == "__main__":
    unittest.main()
