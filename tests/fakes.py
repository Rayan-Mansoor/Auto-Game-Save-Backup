"""Shared fakes for tests that drive sessions and the runner."""

import itertools

from saveix.core.sessions import ProcessInfo


class FakeProcesses:
    def __init__(self):
        self.current = []

    def processes(self):
        return list(self.current)

    def start(self, name, pid=1):
        self.current.append(ProcessInfo(pid, name))

    def stop_all(self):
        self.current = []


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def counting_timestamps():
    counter = itertools.count(1)
    return lambda: f"2026-01-01T00:{next(counter):05d}Z"
