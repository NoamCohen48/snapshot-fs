# CLI Troubleshooting

[Command-line guide](index.md)

## Exit Statuses

| Status | Meaning |
| --- | --- |
| `0` | Command completed successfully. |
| `1` | Import, source, store, registry, or FUSE runtime failure. |
| `2` | Invalid command usage, option, argument, or choice. |
| `130` | The command was interrupted. |

## Contextual Arguments Are Missing

`INPUT`, `--encoding`, and `--date-format` appear in help only after selecting
their source and parser:

```bash
snapshotfs sqlite create --source file --parser windows-dir --help
```

Both `--source` and `--parser` are required. SnapshotFS deliberately performs no
format detection.

## Import Diagnostics

Parser and validation failures have a severity, optional source line, stable
code, and message:

```text
error: line 12: CODE: explanation
```

Imports are all-or-nothing. A failed create does not expose a partial snapshot.
At most 1,000 diagnostics are retained for display, while the total count still
includes additional diagnostics.

## FUSE Is Unavailable

Mounting requires Linux, libfuse 3, `/dev/fuse`, suitable permissions, and the
optional Python dependencies. On Debian or Ubuntu:

```bash
sudo apt install fuse3 libfuse3-dev pkg-config
uv sync --extra fuse
```

The mountpoint must exist, be empty, and not already be mounted. Create one
owned by your user with `mkdir -p /tmp/snapshotfs`. If `/dev/fuse` is absent,
load the host module with `sudo modprobe fuse`. If `fusermount3` is absent,
install `fuse3`. For device permission errors, check `ls -l /dev/fuse` and the
host's device access policy. SnapshotFS reports these setup problems before
starting the mount.

Linux release packages include Python and its FUSE bindings. Install the `.deb`
with `sudo apt install ./snapshotfs_VERSION_amd64.deb` or the Arch package with
`sudo pacman -U ./snapshotfs-VERSION-1-x86_64.pkg.tar.zst` to resolve system
dependencies. A plain Linux binary still needs the host `fuse3` package.

Containers must expose the host FUSE device and allow mounting. For a disposable
Docker test container use `--device /dev/fuse --cap-add SYS_ADMIN` and, on
AppArmor hosts, `--security-opt apparmor=unconfined`. Installing packages inside
a container cannot enable a missing host kernel module. Mounting is Linux-only;
macOS and Windows binaries can create artifacts to mount on Linux.

## Files Cannot Be Read

Directory listings usually contain sizes but not bytes. Reading a non-empty file
with unavailable content returns `ENODATA` by default. See
[missing file content](../concepts/missing-content.md) for the explicit
zero-filled simulation mode and its limitations.

## Doctor And Diagnostic Logs

Start with a read-only environment check:

```bash
snapshotfs --version
snapshotfs doctor
snapshotfs doctor --mountpoint /tmp/snapshotfs
```

`doctor` reports each check separately and exits `1` if any required check fails.
It checks Linux support, Python FUSE bindings, `fusermount3`, `/dev/fuse` and
read/write access, plus whether an optional mountpoint exists, is empty and
accessible, and is not already mounted. It does not modify the host or attempt a
mount; container/kernel restrictions can still prevent a real mount.

Commands write diagnostic logs automatically. On Linux the default is
`$XDG_STATE_HOME/snapshotfs/snapshotfs.log`, or
`~/.local/state/snapshotfs/snapshotfs.log` when `XDG_STATE_HOME` is unset. On
macOS/Windows the log is in the platform application configuration directory;
`doctor` prints the default location. Logs rotate at 2 MiB, keeping three backup
files. A failure to open the default log produces a warning; an explicitly
requested log file must be writable.

Put global logging options **before** the command:

```bash
snapshotfs --verbose --log-file ./mount-debug.log sqlite mount backup.snapshot /tmp/snapshotfs
snapshotfs -v --log-file ./import-debug.log sqlite create backup.snapshot \
  --source file listing.txt --parser windows-dir --encoding cp1252 --date-format mdy
```

`--verbose` (`-v`) sends diagnostic logs and tracebacks to stderr. Normal stdout
(including JSON output) remains suitable for scripts. File logs include the
version/platform, selected components and settings, import progress, mount and
unmount events, FUSE runtime logs, and exception tracebacks. Failed commands
print the log location. Ctrl-C keeps its normal interrupt behavior.

Import diagnostics include bounded, escaped excerpts of the offending decoded
line when available, along with hints for encoding, date format, English
`dir /s` syntax, and missing summaries. Decode failures report the byte offset
and encoding instead of guessing decoded text. No settings are inferred or
changed automatically. Logs may contain source paths and listing excerpts;
check them before attaching to a bug report.
