"""`saveix run` command."""

import logging
import threading

import typer

from saveix.cli.common import open_catalog
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
    with open_catalog(config) as catalog:
        runner = Runner(catalog, BackupEngine(catalog, ObjectStore(config.backup_root)))
        try:
            runner.run(stop, interval)
        except KeyboardInterrupt:
            typer.echo("Stopped.")
