import pytest

from saveix.core.catalog import Catalog, CatalogError, migrations
from saveix.core.models import Source, SourceKind, SourceRole


@pytest.fixture
def catalog(tmp_path):
    with Catalog(tmp_path / "catalog.sqlite3") as cat:
        yield cat


def test_schema_version_matches_migrations(catalog):
    version = catalog.db.execute("PRAGMA user_version").fetchone()[0]
    assert version == len(migrations.MIGRATIONS)


def test_reopening_does_not_reapply_migrations(tmp_path):
    path = tmp_path / "catalog.sqlite3"
    with Catalog(path) as cat:
        cat.add_game("Hollow Knight")
    with Catalog(path) as cat:
        assert [g.name for g in cat.list_games()] == ["Hollow Knight"]


def test_game_names_are_unique_ignoring_case(catalog):
    catalog.add_game("Celeste")
    with pytest.raises(CatalogError):
        catalog.add_game("celeste")
    assert catalog.get_game("CELESTE").name == "Celeste"


def test_empty_name_rejected(catalog):
    with pytest.raises(CatalogError):
        catalog.add_game("  ")


def test_sources_round_trip(catalog):
    game = catalog.add_game("Witcher")
    catalog.add_source(
        game,
        Source(SourceKind.GLOB, "<documents>/The Witcher 3/gamesaves/*.sav", exclude=["*.tmp"]),
    )
    catalog.add_source(
        game, Source(SourceKind.FILE, "<documents>/The Witcher 3/user.settings", SourceRole.CONFIG)
    )

    sources = catalog.get_game("witcher").sources
    assert [s.kind for s in sources] == [SourceKind.GLOB, SourceKind.FILE]
    assert sources[0].exclude == ["*.tmp"]
    assert sources[1].role is SourceRole.CONFIG
    assert sources[0].origin == "manual"


def test_duplicate_source_rejected(catalog):
    game = catalog.add_game("G")
    catalog.add_source(game, Source(SourceKind.FOLDER, "<appdata>/G"))
    with pytest.raises(CatalogError):
        catalog.add_source(game, Source(SourceKind.FOLDER, "<appdata>/G"))


def test_removing_game_removes_its_sources(catalog):
    game = catalog.add_game("G")
    catalog.add_source(game, Source(SourceKind.FOLDER, "<appdata>/G"))
    catalog.remove_game("G")
    assert catalog.db.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 0


def test_remove_source(catalog):
    game = catalog.add_game("G")
    source = catalog.add_source(game, Source(SourceKind.FOLDER, "<appdata>/G"))
    catalog.remove_source(game, source.id)
    assert catalog.get_game("G").sources == []
    with pytest.raises(CatalogError):
        catalog.remove_source(game, source.id)
