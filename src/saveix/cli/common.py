"""Helpers shared by CLI commands."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import NoReturn

import typer

from saveix.core.catalog import Catalog, CatalogError
from saveix.core.config import Config


def fail(message: str) -> NoReturn:
    typer.echo(message, err=True)
    raise typer.Exit(1)


@contextmanager
def open_catalog(config: Config | None = None) -> Iterator[Catalog]:
    """Open the catalog and turn catalog errors into clean CLI errors."""
    config = config or Config()
    catalog = Catalog(config.catalog_path)
    try:
        yield catalog
    except CatalogError as exc:
        fail(str(exc))
    finally:
        catalog.close()
