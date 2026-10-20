# SaveIX

Automatic, versioned backups of local game save files on Windows.

Games that keep their progress only on your PC (offline, DRM-free and other local-only copies)
can lose everything when a save file gets corrupted. SaveIX watches your play sessions,
takes snapshots of each game's save files at checkpoints and when you stop playing,
and lets you restore the latest progress or any earlier stage.

> Status: early development. Only the project skeleton exists so far.

## Development

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync                 # create the virtual environment
uv run saveix --version
uv run pytest           # run tests
uv run ruff check .     # lint
```
