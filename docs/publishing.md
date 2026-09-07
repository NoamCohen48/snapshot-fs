# Publishing The Documentation

[Documentation](index.md)

The site is built with Sphinx, MyST-Parser, and Furo. Authored pages remain
ordinary Markdown under `docs/`.

## Local Preview

```bash
uv sync --all-groups
uv run sphinx-autobuild docs docs/_build/html
```

Open the URL printed by `sphinx-autobuild`. For the same strict build used by
automation:

```bash
uv run python scripts/generate_cli_reference.py --check
uv run sphinx-build -W --keep-going -b html docs docs/_build/html
```

Regenerate CLI help after changing commands or component parameters:

```bash
uv run python scripts/generate_cli_reference.py
```

## Read The Docs

The repository's `.readthedocs.yaml` installs the locked `docs` dependency group
with uv and builds `docs/conf.py`. To publish a public project:

1. Import the GitHub repository at [Read the Docs](https://readthedocs.org/).
2. Enable the default branch and release tags that should be public.
3. Require the documentation build before merging changes that affect docs.

Read the Docs provides versioned builds, search, pull-request previews, and
downloadable documentation. Sphinx emits static HTML, so the same build output
can instead be hosted on GitHub Pages or any static web host.
