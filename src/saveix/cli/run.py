"""`saveix run` command."""

import logging
import threading

import typer

from saveix.cli.common import open_catalog
from saveix.cli.prune import retention_hook
from saveix.core.backup import BackupEngine
from saveix.core.config import Config
from saveix.core.daemon import Runner
from saveix.core.store import ObjectStore


def run(
    interval: float = typer.Option(5.0, help="Seconds between checks for running games."),
) -> None:
    """Watch for play sessions and back up saves automatically (Ctrl+C to stop)."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    config = Config()
    stop = threading.Event()
    _lower_priority()
    with open_catalog(config) as catalog:
        runner = Runner(
            catalog,
            BackupEngine(catalog, ObjectStore(config.backup_root)),
            quiet_period=config.settings.quiet_period_seconds,
            checkpoint_interval=config.settings.checkpoint_interval_minutes * 60,
            retention=retention_hook(config, catalog),
        )
        try:
            runner.run(stop, interval)
        except KeyboardInterrupt:
            typer.echo("Stopped.")


def _lower_priority() -> None:
    """Keep backups from competing with the game for CPU and disk."""
    import sys

    import psutil

    me = psutil.Process()
    try:
        if sys.platform == "win32":
            me.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
            me.ionice(psutil.IOPRIO_LOW)
        else:
            me.nice(10)
    except (psutil.Error, OSError, AttributeError):
        pass


def tray() -> None:
    """Run saveix in the system tray (needs the gui extra)."""
    try:
        from saveix.ui.tray import main
    except ImportError as exc:
        typer.echo(f"The tray app needs PySide6 (pip install saveix[gui]): {exc}", err=True)
        raise typer.Exit(1) from None
    raise typer.Exit(main())


def gui() -> None:
    """Open the saveix window (needs the gui extra)."""
    try:
        from saveix.ui.main_window import main
    except ImportError as exc:
        typer.echo(f"The window needs PySide6 (pip install saveix[gui]): {exc}", err=True)
        raise typer.Exit(1) from None
    raise typer.Exit(main())
