"""`saveix mirror` command."""

from pathlib import Path

import typer

from saveix.cli.common import fail, open_catalog
from saveix.core.config import Config
from saveix.core.mirror import mirror as mirror_backups
from saveix.core.store import ObjectStore
from saveix.core.text import human_size


def mirror(
    folder: str | None = typer.Argument(
        None, help="Folder to copy backups to; defaults to the mirror_dir setting."
    ),
) -> None:
    """Copy all backups to a second folder, such as one synced by OneDrive."""
    config = Config()
    target = folder or config.settings.mirror_dir
    if not target:
        fail("Give a folder, or set one with `saveix config set mirror_dir FOLDER`.")
    with open_catalog(config) as catalog:
        report = mirror_backups(catalog, ObjectStore(config.backup_root), Path(target).expanduser())
    typer.echo(
        f"Mirror updated: {report.copied} new files ({human_size(report.bytes)}), "
        f"{report.removed} removed."
    )
