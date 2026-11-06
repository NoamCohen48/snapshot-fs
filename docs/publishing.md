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

## GitHub releases

Pull requests run the test matrix, wheel installation smoke test, strict docs
build, and standalone binary builds before merging. In GitHub branch protection,
require these checks for the default branch.

To release, update `project.version` in `pyproject.toml`, refresh `uv.lock` with
`uv lock`, merge the passing PR, then push the matching tag (for example
`git tag v0.1.0` and `git push origin v0.1.0`). The release workflow verifies the
tag matches the package version and publishes only after all checks pass.

Releases contain the SDK wheel and source distribution, `snapshotfs-sdk.tgz`
containing both Python packages, `snapshotfs-docs.tgz` with offline HTML docs,
and platform-specific `snapshotfs-cli-*.tgz` archives containing a standalone
executable. Extract the CLI archive and run `snapshotfs --help`; no Python
installation is needed. SHA256SUMS covers all downloadable packages.

The Linux standalone CLI bundles Python and the `fuse` extra. It supports
mounting on a host with `fuse3`, `/dev/fuse`, and mount permissions. Debian and
Arch packages wrap this executable and declare system FUSE dependencies.
macOS and Windows binaries support import and inspection only. macOS builds target
Apple Silicon; Linux builds target x86-64 with glibc 2.35 or newer. Windows
archives contain `snapshotfs.exe`. Binaries are currently unsigned.

Install the SDK wheel with `pip install snapshotfs-0.1.0-py3-none-any.whl`
(adjust the filename for the release). The wheel also installs the Python CLI
and includes SDK type information.

The same wheel provides the SDK and the CLI entry point. CLI users can install
it with pipx or run it with uvx without installing the SDK into their project:

```bash
pipx install ./snapshotfs-0.1.0-py3-none-any.whl
snapshotfs --help
uvx --from ./snapshotfs-0.1.0-py3-none-any.whl snapshotfs --help
```

Use the downloaded release wheel filename. These commands install directly from
the wheel; the release workflow does not publish to PyPI.

## Linux Distribution Packages

Linux releases also provide `snapshotfs_VERSION_amd64.deb` and
`snapshotfs-VERSION-1-x86_64.pkg.tar.zst`. Both contain the standalone Linux
executable and the example listing, and depend on `fuse3` and glibc >= 2.35.
They bundle Python dependencies rather than relying on each distribution's
Python package versions. Build the Linux executable on Ubuntu 22.04 to preserve
the documented glibc baseline; binaries built on newer hosts may require newer
glibc. The Debian builder is `packaging/debian/build.sh`; the Arch recipe is
`packaging/arch/PKGBUILD` and consumes the frozen executable. CI substitutes the
release version and input SHA256 hashes before running `makepkg` as an
unprivileged user. The packages are unsigned; no apt repository or AUR
publication is configured.

CI exercises real memory and SQLite FUSE mounts, directory listing, stat,
missing-content errors, optional zero-filled reads, read-only behavior, and
unmounting. The same integration test can target an installed executable:

```bash
SNAPSHOTFS_MOUNT_TEST=1 SNAPSHOTFS_TEST_CLI=/usr/bin/snapshotfs \
  uv run --extra fuse pytest -q tests/test_mount_integration.py
```
