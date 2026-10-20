"""Tests for environment bootstrapping and virtual environment management."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from openstick.bootstrap import (
    is_in_venv,
    check_missing_modules,
    get_venv_executables,
    ensure_environment,
)


class TestBootstrap(unittest.TestCase):
    def test_is_in_venv_returns_bool(self):
        result = is_in_venv()
        self.assertIsInstance(result, bool)

    def test_check_missing_modules_known(self):
        # sys and os are built-in and always available
        missing = check_missing_modules(["sys", "os"])
        self.assertEqual(len(missing), 0)

        # Non-existent module must be detected
        missing = check_missing_modules(["non_existent_module_xyz_123"])
        self.assertIn("non_existent_module_xyz_123", missing)

    def test_get_venv_executables(self):
        dummy_dir = Path("/tmp/fake_venv")
        py_bin, pip_bin = get_venv_executables(dummy_dir)
        if sys.platform == "win32":
            self.assertEqual(py_bin.name, "python.exe")
            self.assertEqual(pip_bin.name, "pip.exe")
        else:
            self.assertEqual(py_bin.name, "python")
            self.assertEqual(pip_bin.name, "pip")

    def test_ensure_environment_dry_run(self):
        self.assertTrue(ensure_environment(dry_run=True))


if __name__ == "__main__":
    unittest.main()
