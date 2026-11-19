"""Ctrl-C / SIGTERM must stop the EDL child cleanly and exit without a traceback."""

import io
import signal
import unittest
from unittest.mock import patch

import main as main_module
from openstick import edl
from openstick.edl import run_edl_command
from tests.fakes import FakeProcess


class TestGracefulShutdown(unittest.TestCase):
    def test_ctrl_c_mid_command_kills_child_and_propagates(self):
        proc = FakeProcess(interrupt=True)
        with patch("openstick.edl.find_edl_runner", return_value=["edl"]), \
             patch("openstick.edl.subprocess.Popen", return_value=proc), \
             patch("sys.stdout", io.StringIO()):
            with self.assertRaises(KeyboardInterrupt):
                run_edl_command(["rf", "full_emmc.bin"])

        self.assertTrue(proc.terminated)

    def test_sigterm_cancels_the_run_and_stops_the_running_child(self):
        proc = FakeProcess()
        handlers = {}

        def main_receives_sigterm():
            handlers[signal.SIGTERM](signal.SIGTERM, None)

        with patch.object(edl, "_active_edl_processes", [proc]), \
             patch("main.main", side_effect=main_receives_sigterm), \
             patch("main.signal.signal", side_effect=lambda sig, handler: handlers.__setitem__(sig, handler)), \
             patch("sys.stderr", io.StringIO()):
            self.assertEqual(main_module.run_cli(), 130)

        self.assertTrue(proc.terminated)


if __name__ == "__main__":
    unittest.main()
