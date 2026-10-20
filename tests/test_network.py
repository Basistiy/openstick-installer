"""Tests for network discovery and SSH verification."""

import unittest
from unittest.mock import patch, MagicMock

from openstick.network import (
    get_candidate_ips,
    find_stick_device,
    wait_for_debian_boot,
    DEFAULT_CANDIDATE_IPS,
)


class TestNetwork(unittest.TestCase):
    def test_get_candidate_ips_includes_defaults(self):
        candidates = get_candidate_ips()
        for ip in DEFAULT_CANDIDATE_IPS:
            self.assertIn(ip, candidates)

    def test_find_stick_device_dry_run(self):
        res = find_stick_device(dry_run=True)
        self.assertIsNotNone(res)
        ip, banner = res
        self.assertEqual(ip, "192.168.5.1")
        self.assertIn("SSH", banner)

    def test_wait_for_debian_boot_dry_run(self):
        ip = wait_for_debian_boot(timeout=2, dry_run=True)
        self.assertEqual(ip, "192.168.5.1")


if __name__ == "__main__":
    unittest.main()
