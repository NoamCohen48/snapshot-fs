# Setup And Checks

[Development](README.md)

SnapshotFS requires Python 3.12 or newer and uses
[uv](https://docs.astral.sh/uv/) for dependency management and commands.

## Environment

Create the development environment with all development dependencies:

```bash
uv sync --all-groups
```

The filesystem adapter requires Linux, libfuse 3 development headers, and its
optional dependencies:

```bash
uv sync --all-groups --extra fuse
```

## Checks

Run the full test suite, linting, and static type checking before submitting a
change:

```bash
uv run pytest
uv run ruff check .
uv run mypy src
```

Build the documentation and verify that its generated CLI reference is current:

```bash
uv run python scripts/generate_cli_reference.py --check
uv run sphinx-build -W --keep-going -b html docs docs/_build/html
```

For a live-reloading local documentation server, run:

```bash
uv run sphinx-autobuild docs docs/_build/html
```

Kernel-level mount tests may be skipped when FUSE, `/dev/fuse`, or the required
permissions are unavailable. Unit tests for the adapter do not require a kernel
mount.
