"""Tests for device models and board definitions."""

import unittest
from openstick.devices import get_device_by_id, get_device_by_index, get_supported_devices


class TestDevices(unittest.TestCase):
    def test_get_supported_devices(self):
        devices = get_supported_devices()
        self.assertIn("uz801", devices)
        self.assertIn("hmuf02", devices)
        self.assertEqual(len(devices), 2)

    def test_get_uz801_by_id(self):
        dev = get_device_by_id("uz801")
        self.assertIsNotNone(dev)
        self.assertEqual(dev.id, "uz801")
        self.assertEqual(dev.recommended_loader, "prog_emmc_firehose_8916.mbn")
        self.assertIn("modemst1", dev.critical_partitions)
        self.assertIn("modemst2", dev.critical_partitions)
        self.assertIn("fsg", dev.critical_partitions)
        self.assertIn("fsc", dev.critical_partitions)

    def test_get_hmuf02_by_id_and_aliases(self):
        dev = get_device_by_id("hmuf02")
        self.assertIsNotNone(dev)
        self.assertEqual(dev.id, "hmuf02")
        self.assertEqual(dev.recommended_loader, "prog_emmc_firehose_8916.mbn")
        for part in ("modemst1", "modemst2", "fsg", "fsc", "persist", "sec"):
            self.assertIn(part, dev.critical_partitions)

        for alias in ("HMUF02", "hmuf", "HMUF02-V05"):
            resolved = get_device_by_id(alias)
            self.assertIsNotNone(resolved)
            self.assertEqual(resolved.id, "hmuf02")

    def test_case_insensitivity(self):
        dev_upper = get_device_by_id("UZ801")
        self.assertIsNotNone(dev_upper)
        self.assertEqual(dev_upper.id, "uz801")

        dev_mixed = get_device_by_id("  Uz801  ")
        self.assertIsNotNone(dev_mixed)
        self.assertEqual(dev_mixed.id, "uz801")

    def test_unknown_device_returns_none(self):
        self.assertIsNone(get_device_by_id("unknown_board"))
        self.assertIsNone(get_device_by_id(""))

    def test_get_by_index(self):
        dev1 = get_device_by_index(1)
        self.assertIsNotNone(dev1)
        self.assertEqual(dev1.id, "uz801")

        dev2 = get_device_by_index(2)
        self.assertIsNotNone(dev2)
        self.assertEqual(dev2.id, "hmuf02")

        self.assertIsNone(get_device_by_index(0))
        self.assertIsNone(get_device_by_index(99))


if __name__ == "__main__":
    unittest.main()
