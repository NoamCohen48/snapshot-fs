# Getting Started

Mount a filesystem listing on Linux, then browse its names and metadata with
ordinary filesystem tools. A listing is not a backup: it does not contain the
original file bytes.

## Install On Linux

Download a package from GitHub Releases. Debian/Ubuntu (glibc 2.35 or newer):

```bash
sudo apt install ./snapshotfs_0.1.0_amd64.deb
```

Arch Linux:

```bash
sudo pacman -U ./snapshotfs-0.1.0-1-x86_64.pkg.tar.zst
```

Adjust filenames for the release. These x86-64 packages include Python and its
FUSE bindings, and install the host `fuse3` dependency. No pip setup is needed.
The host must expose `/dev/fuse` and permit FUSE mounts. macOS and Windows release
binaries support creating and inspecting artifacts; mounting is Linux-only.

From a source checkout instead:

```bash
sudo apt install fuse3 libfuse3-dev pkg-config
uv sync --all-groups --extra fuse
```

Prefix the commands below with `uv run` when working from a checkout.

## Mount The Included Example

The Linux packages install a small example at
`/usr/share/doc/snapshotfs/examples/windows-dir.txt`. From a checkout, use
`examples/windows-dir.txt` instead.

```bash
mkdir -p /tmp/snapshotfs-demo
snapshotfs memory mount /tmp/snapshotfs-demo \
  --source file /usr/share/doc/snapshotfs/examples/windows-dir.txt \
  --parser windows-dir --encoding utf-8 --date-format mdy
```

The command stays in the foreground. In another terminal:

```bash
ls -l /tmp/snapshotfs-demo/C/Users/Alice
stat '/tmp/snapshotfs-demo/C/Users/Alice/notes file.txt'
find /tmp/snapshotfs-demo -type f
```

The example contains `notes file.txt` (1,234 bytes) and `Documents/todo.txt`
(8 bytes). Their names, sizes, and timestamps are available, but reading their
contents returns `ENODATA` (often displayed as “No data available”). Writes fail
because the filesystem is read-only.

Stop the mount with Ctrl-C in its terminal, or run:

```bash
fusermount3 -u /tmp/snapshotfs-demo
```

Only if a consumer requires readable placeholders, add
`--simulate-missing-content` to the mount command. Reads then return zero bytes
up to the listed size; these are not recovered file contents.

## Mount Your Own Listing

The built-in parser accepts English Windows `dir /s` output:

```batch
dir C:\Path\To\Inventory /s > listing.txt
```

Choose the encoding and date order for the machine that produced the listing;
SnapshotFS does not guess them. Preserve it as a validated artifact and mount:

```bash
snapshotfs sqlite create backup.snapshot \
  --source file listing.txt --parser windows-dir \
  --encoding cp1252 --date-format mdy
mkdir -p /tmp/snapshotfs
snapshotfs sqlite mount backup.snapshot /tmp/snapshotfs
```

Creation is atomic and refuses to replace an existing artifact unless
`--overwrite` is supplied. The SQLite artifact can be shared and mounted later
without the source listing. See [troubleshooting](cli/troubleshooting.md) for
host setup and [the CLI guide](cli/index.md) for other workflows.

## Platform Support

| Installation | Create / inspect | FUSE mount | Python setup |
| --- | --- | --- | --- |
| Linux x86-64 `.deb` / Arch package | Yes | Yes, with host FUSE access | Bundled |
| Linux x86-64 `.tgz` executable | Yes | Yes, install host `fuse3` | Bundled |
| macOS ARM64 / Windows x86-64 executable | Yes | No | Bundled |
| SDK / CLI wheel | Yes | Linux with `[fuse]` and host `fuse3` | Python >= 3.12 |
