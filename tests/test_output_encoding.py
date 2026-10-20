import os
import subprocess
import sys


def test_timeline_survives_a_legacy_code_page(fake_home, tmp_path):
    """Windows pipes and redirects use the ANSI code page, which has no ✓ or ⚠."""
    saves = fake_home / "AppData/Roaming/G"
    saves.mkdir(parents=True)
    (saves / "s.sav").write_text("x")
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}

    def run(*args):
        return subprocess.run(
            [sys.executable, "-m", "saveix", *args],
            capture_output=True,
            env=env,
            check=False,
        )

    run("game", "add", "G")
    run("source", "add", "G", str(saves))
    run("backup", "G")
    result = run("timeline", "G")
    assert result.returncode == 0, result.stderr.decode("cp1252", "replace")
    assert b"#1" in result.stdout
