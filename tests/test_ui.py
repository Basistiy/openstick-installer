"""Tests for User Interface presentation and menu handlers."""

import io
import sys
import unittest
from unittest.mock import patch

from openstick.ui import (
    print_banner,
    print_disclaimer,
    show_flashing_warning,
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
        self.assertIn("https://github.com/Basistiy/openstick-installer/issues", output)
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

    def test_print_disclaimer(self):
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            print_disclaimer()
        output = captured.getvalue()
        self.assertIn("WARNING & DISCLAIMER", output)
        self.assertIn("risky process", output)
        self.assertIn("NOT responsible", output)
        self.assertIn("outcomes", output)

    def test_show_flashing_warning_linux(self):
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            show_flashing_warning(mode="linux")
        output = captured.getvalue()
        self.assertIn("WARNING: Flashing Linux is a risky process", output)
        self.assertIn("NOT responsible", output)
        self.assertIn("outcomes", output)

    def test_show_flashing_warning_stock(self):
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            show_flashing_warning(mode="stock")
        output = captured.getvalue()
        self.assertIn("WARNING: Flashing firmware is a risky process", output)
        self.assertIn("NOT responsible", output)

    def test_print_banner_includes_disclaimer(self):
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            print_banner()
        output = captured.getvalue()
        self.assertIn("MSM8916 Linux Installer", output)
        self.assertIn("WARNING & DISCLAIMER", output)
        self.assertIn("NOT responsible", output)


if __name__ == "__main__":
    unittest.main()
