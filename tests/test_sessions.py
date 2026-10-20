from typer.testing import CliRunner

from saveix.cli import app
from saveix.core.models import Game
from saveix.core.sessions import (
    EventKind,
    ProcessInfo,
    SessionDetector,
    matches_game,
    running_games,
)

runner = CliRunner()


class FakeProcesses:
    def __init__(self):
        self.current = []

    def processes(self):
        return list(self.current)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def game(**kwargs):
    defaults = {"name": "G", "id": 1}
    defaults.update(kwargs)
    return Game(**defaults)


def proc(pid, name, exe=None, *cmdline):
    return ProcessInfo(pid, name, exe, tuple(cmdline))


def test_matching_by_name_path_and_install_folder():
    by_name = game(executables=["HollowKnight.exe"])
    assert matches_game(by_name, proc(1, "hollowknight.exe"))
    assert matches_game(by_name, proc(1, "x", "C:\\Games\\HK\\HollowKnight.exe"))
    assert not matches_game(by_name, proc(1, "other.exe"))

    by_path = game(executables=["D:/Games/G/bin/g.exe"])
    assert matches_game(by_path, proc(1, "g.exe", "d:\\games\\g\\BIN\\g.exe"))
    assert not matches_game(by_path, proc(1, "g.exe", "C:/elsewhere/g.exe"))

    by_folder = game(install_dir="D:/Games/G")
    assert matches_game(
        by_folder, proc(1, "G-Win64-Shipping.exe", "D:\\Games\\G\\Bin\\G-Win64-Shipping.exe")
    )
    assert not matches_game(by_folder, proc(1, "x.exe", "D:/Games/Gother/x.exe"))
    assert not matches_game(
        by_folder, proc(1, "UnityCrashHandler64.exe", "D:/Games/G/UnityCrashHandler64.exe")
    )


def test_session_start_and_end_with_grace_period():
    procs, clock = FakeProcesses(), FakeClock()
    detector = SessionDetector(procs, end_grace_seconds=10, clock=clock)
    g = game(executables=["g.exe"])

    assert detector.poll([g]) == []
    procs.current = [proc(10, "g.exe")]
    events = detector.poll([g])
    assert [e.kind for e in events] == [EventKind.STARTED]
    assert detector.is_running(g)

    procs.current = []
    clock.now = 5
    assert detector.poll([g]) == []
    clock.now = 16
    events = detector.poll([g])
    assert [(e.kind, e.crashed) for e in events] == [(EventKind.ENDED, False)]
    assert not detector.is_running(g)


def test_launcher_handover_is_one_session():
    procs, clock = FakeProcesses(), FakeClock()
    detector = SessionDetector(procs, end_grace_seconds=10, clock=clock)
    g = game(install_dir="C:/Games/G")
    procs.current = [proc(1, "launcher.exe", "C:/Games/G/launcher.exe")]
    detector.poll([g])
    procs.current = []
    clock.now = 3
    detector.poll([g])
    procs.current = [proc(2, "G-Win64-Shipping.exe", "C:/Games/G/Bin/G-Win64-Shipping.exe")]
    clock.now = 6
    assert detector.poll([g]) == []
    procs.current = []
    clock.now = 20
    detector.poll([g])
    clock.now = 31
    assert [e.kind for e in detector.poll([g])] == [EventKind.ENDED]


def test_crash_is_noticed():
    procs, clock = FakeProcesses(), FakeClock()
    detector = SessionDetector(procs, end_grace_seconds=0, clock=clock)
    g = game(executables=["g.exe"])
    procs.current = [proc(42, "g.exe")]
    detector.poll([g])
    procs.current = [
        proc(42, "g.exe"),
        proc(99, "WerFault.exe", None, "WerFault.exe", "-u", "-p", "42"),
    ]
    detector.poll([g])
    procs.current = []
    events = detector.poll([g])
    assert [(e.kind, e.crashed) for e in events] == [(EventKind.ENDED, True)]


def test_running_games():
    procs = FakeProcesses()
    procs.current = [proc(1, "a.exe")]
    a, b = game(name="A", id=1, executables=["a.exe"]), game(name="B", id=2, executables=["b.exe"])
    assert running_games([a, b], procs) == [a]


def test_exe_commands(fake_home):
    runner.invoke(app, ["game", "add", "G"])
    assert runner.invoke(app, ["game", "add-exe", "G", "G.exe"]).exit_code == 0
    assert runner.invoke(app, ["game", "add-exe", "G", "g.EXE"]).exit_code == 1
    assert "executables: G.exe" in runner.invoke(app, ["game", "show", "G"]).output
    assert runner.invoke(app, ["game", "remove-exe", "G", "g.exe"]).exit_code == 0
    assert runner.invoke(app, ["game", "remove-exe", "G", "g.exe"]).exit_code == 1
    assert "None of your games are running" in runner.invoke(app, ["game", "running"]).output
