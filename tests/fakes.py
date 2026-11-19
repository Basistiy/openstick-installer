"""Shared stand-ins used by the tests."""


class FakeProcess:
    """Minimal subprocess.Popen lookalike; `interrupt` makes communicate raise Ctrl-C."""

    def __init__(self, returncode=None, stdout="", stderr="", interrupt=False):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.interrupt = interrupt
        self.terminated = False

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def communicate(self, timeout=None):
        if self.interrupt:
            raise KeyboardInterrupt
        if self.returncode is None:
            self.returncode = 0
        return self.stdout, self.stderr

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.terminated = True
        self.returncode = -9
