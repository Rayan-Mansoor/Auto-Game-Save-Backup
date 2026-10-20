from typer.testing import CliRunner

from saveix import __version__
from saveix.cli import app

runner = CliRunner()


def test_version_option_prints_version():
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == f"saveix {__version__}"
