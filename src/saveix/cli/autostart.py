"""`saveix autostart` command."""

import typer

from saveix.cli.common import fail
from saveix.core import autostart as auto


def autostart(
    state: str = typer.Argument("status", help="on, off or status"),
) -> None:
    """Start saveix in the tray when you log in to Windows."""
    try:
        if state == "on":
            command = auto.enable()
            typer.echo(f"saveix will start with Windows ({command}).")
        elif state == "off":
            auto.disable()
            typer.echo("saveix will no longer start with Windows.")
        elif state == "status":
            on = auto.is_enabled()
            typer.echo("Starts with Windows." if on else "Does not start with Windows.")
        else:
            fail("Use on, off or status.")
    except auto.AutostartUnavailableError as exc:
        fail(str(exc))
