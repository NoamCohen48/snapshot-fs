# SnapshotFS Architecture

## Purpose

SnapshotFS imports a textual or binary description of a computer's filesystem,
normalizes it, and exposes the result as a read-only userspace filesystem. Input
acquisition, parsing, storage, and mounting are separate layers so that new
sources and formats can be added independently.

The first release targets Linux, Python 3.12 or newer, libfuse 3, local file
sources, and Windows `dir /s` listings with English structural labels. The
listing contains metadata, not file bytes, so imported non-empty files can be
inspected but cannot be read by default. An explicit simulation mode may return
zero-filled stand-in data without claiming it is original content.

## Pipeline

```text
Source -> Parser (optional decoder) -> Import service -> Snapshot builder/store -> FUSE adapter
```

Each boundary operates on explicit domain objects. A parser owns any decoding
its format needs, allowing later binary parsers to consume source bytes
directly. Parsers never call FUSE, and the FUSE adapter never interprets source
formats.

## Python FUSE Library

SnapshotFS will use [pyfuse3](https://github.com/libfuse/pyfuse3) with Trio.

The alternatives considered were:

| Library | Decision | Reason |
| --- | --- | --- |
| pyfuse3 | Selected | Maintained libfuse 3 bindings, typed low-level inode API, efficient async request handling, and a stable Trio integration. |
| mfusepy | Not selected | Maintained and simpler, but its synchronous path-based high-level API is a poorer match for an indexed inode store and future remote content. |
| fusepy | Rejected | Last PyPI release was in 2018 and the project still carries Python 2-era design constraints. |
| llfuse | Rejected | Superseded for this use case by pyfuse3 and no longer actively developed upstream. |

pyfuse3 is in maintenance mode rather than active feature development. This is
acceptable because the libfuse API is mature and maintainers state that bugs
and compatibility with new Python and libfuse versions continue to be handled.
The FUSE adapter remains isolated so this choice can be revisited.

## Domain Model

The normalized model is independent of any source format:

```text
Snapshot
  id
  source_uri
  source_format
  imported_at
  source_metadata

Node
  id
  snapshot_id
  parent_id
  mounted_name: bytes
  original_path: optional string
  kind: directory | file | symlink | special | unknown
  size: optional integer
  modified_at: optional timestamp
  content: optional bytes
  content_status: not_applicable | missing | present | remote | failed | redacted
  content_ref: optional string
  source_metadata

ImportDiagnostic
  severity: warning | error
  line_number: optional integer
  code
  message

ParsedEntry
  path: tuple[str, ...]
  kind: directory | file
  observation: section_header | directory_entry | file_entry
  size: optional integer
  modified_local: optional naive datetime
  source_line: optional integer
  content: optional bytes
  source_metadata
```

Nodes use parent-child relationships rather than full mounted paths. A unique
constraint on `(parent_id, mounted_name)` protects directory semantics. The
parser-assigned relative mounted path is retained on each node.

`ParsedEntry.path` is the complete tuple of names below the virtual mount root.
Generic builders do not parse separators, roots, drives, URI syntax, or host
paths. They enforce mounted-component safety and synthesize ancestry. Paths are
exact and case-sensitive. This supports POSIX paths, macOS paths, Windows
drives, archives, object keys, and custom namespaces without depending on a
host `pathlib` flavor.

`ParsedEntry` is the parser/import-service boundary. Every `Directory of`
header emits a directory entry with `observation=section_header`, ensuring an
empty section creates a directory even when no parent listing mentions it. A
later `directory_entry` observation may enrich that node with metadata. A
parsed entry contains no inode, parent ID, or mounted-name decision. The import
service validates mount safety, synthesizes ancestry, encodes mounted names, and
assigns IDs while building `Node` objects.

The implementation provides immutable in-memory nodes and a persistent SQLite
store behind the same protocol. The parser and FUSE layers therefore remain
independent of storage details.

## Source Layer

A source supplies bytes and identifies where they came from. The first source
is `FileSource`, which:

- Accepts a local path.
- Opens it in binary mode.
- Exposes a stable source URI and optional size.
- Does not choose an encoding or parse content.
- Propagates missing-file and permission errors with source context.

Future sources may provide HTTP, object storage, stdin, archives, or directory
trees without changing parser contracts.

## Decoding

Text decoding is a parser concern, implemented through a reusable bounded line
decoder. Windows console output commonly uses a Windows code page, while
redirected output from modern tools may be UTF-8 or UTF-16. The initial decoder
accepts UTF-8, UTF-16 with explicit or BOM-selected byte order, ASCII, Latin-1,
and Windows-1250 through Windows-1258; it defaults to UTF-8 with an optional BOM.
Stateful or potentially unbounded buffering codecs such as UTF-7 are rejected
before input is read. Invalid byte sequences are errors rather than silently
replaced characters. A UTF-8 BOM is stripped only at stream offset zero;
interior BOM byte sequences decode to U+FEFF and remain meaningful input.
Automatic code page detection is deferred because it is inherently unreliable.

The CLI will expose `--encoding`, for example:

```bash
snapshotfs sqlite create backup.snapshot --source file listing.txt --parser windows-dir --encoding cp1252
```

## Parser Contract

Parsers consume a binary source stream and emit `ParsedEntry` values and
diagnostics incrementally. Text parsers may wrap the stream in the shared line
decoder; binary parsers do not. A parser exposes:

- A stable format name.
- A parse operation yielding parsed entries without loading the full input.
- Structured errors with line numbers.

SnapshotFS performs no probing or automatic source/format detection. CLI users
must select both implementations with `--source` and `--parser`; library users
construct and pass concrete `Source` and `Parser` objects.

Malformed structural lines and unknown meaningful lines add error diagnostics.
The parser may continue to collect up to 1,000 diagnostics but the import
service discards all entries if any error exists. Lines that are non-semantic
according to the format-specific grammar are ignored deliberately. The Windows
parser treats summaries as validated structural records rather than ignored
lines. A physical line may not exceed 1 MiB of content bytes; the bytes encoding
the terminating LF or CRLF are excluded consistently for single- and multibyte
encodings. Exceeding the limit is a fatal decode error. These defaults are
constants in the first release.

## Windows `dir /s` Format

The initial parser supports a deliberately restricted dialect of native
Windows Command Prompt output: English structural labels and an explicit date
ordering. Date ordering defaults to `mdy` and can be selected with
`--date-format mdy|dmy|ymd`; `/`, `-`, and `.` separators, four-digit years,
and 12- or 24-hour times are accepted. Two-digit years are rejected to avoid an
implicit century pivot. The parsed value is retained as a
naive source-local datetime because `dir` supplies no timezone. JSON emits it as
an ISO 8601 local value without a `Z` or offset. Duplicate comparisons use the
naive value exactly.

Example input:

```text
 Volume in drive C has no label.
 Volume Serial Number is 1234-ABCD

 Directory of C:\Users\Alice

01/02/2024  03:04 PM    <DIR>          Documents
01/02/2024  03:05 PM             1,234 notes.txt
               1 File(s)          1,234 bytes
               3 Dir(s)     10,000,000 bytes free

 Directory of C:\Users\Alice\Documents

01/02/2024  03:06 PM                 8 todo.txt
               1 File(s)              8 bytes
               2 Dir(s)     10,000,000 bytes free

     Total Files Listed:
               2 File(s)          1,242 bytes
               5 Dir(s)     10,000,000 bytes free
```

Parsing rules for the first release are:

- A `Directory of <absolute path>` line starts a directory section.
- Entry timestamps use the configured date ordering and either 12- or 24-hour time.
- `<DIR>` marks directories; a numeric size marks files.
- Thousands separators in sizes are accepted.
- `.` and `..` entries are ignored.
- Drive roots are ordinary first-level components, such as `C/Users/Alice`.
- Parent directories omitted from the listing are synthesized.
- Paths are emitted with their listing spelling and compared exactly.
- Repeated compatible observations of the same component path are merged.
- Conflicting entries are fatal and identify both source lines.
- A later explicit directory entry enriches a synthesized node with timestamp,
  source line and relative-path provenance; incompatible explicit metadata is
  a conflict.
- Volume banners and blank lines are ignored. Per-section `File(s)` and
  `Dir(s)` summaries, `File Not Found`, `Total Files Listed:`, and aggregate
  summaries are parsed as structural records.
- A complete import requires `Total Files Listed:` and both aggregate summary
  lines before EOF. Per-section and aggregate file counts and byte totals are
  validated against parsed file entries. Directory totals are parsed for
  syntax but are not validated because native output may count `.` and `..`
  differently by invocation. Count or byte mismatches are fatal, preventing
  truncated or edited listings from appearing complete.
- Unrecognized or localized structural output is an error with a line number.
- Within a section, entries or a single `File Not Found` marker precede the
  `File(s)` summary, which precedes the `Dir(s)` summary. Entries and
  `File Not Found` cannot be mixed, and no entry is accepted after a summary.
- Aggregate summaries likewise require `File(s)` before `Dir(s)`.

The deterministic entry grammar consumes one separator space after a file size
or the native ten-space field after `<DIR>`, then preserves the complete
filename remainder, including leading spaces. A source name containing NUL,
`/`, `\`, or `:` is rejected; colons are rejected because alternate data streams
are unsupported. Section paths are validated before Windows path construction
so repeated separators and trailing empty components cannot be silently
normalized. The Windows parser emits the drive as the first component of the
relative mounted path. Mounted names are the UTF-8 encoding of those component
strings; pyfuse3 lookup compares the bytes exactly and directory iteration sorts
by those bytes. Compatible repeated observations of the same exact path merge.

## Store Interface

The store supports operations required by import and FUSE:

```python
class SnapshotStore(Protocol):
    diagnostics: tuple[ImportDiagnostic, ...]
    diagnostic_count: int

    def get_snapshot(self, snapshot_id: str) -> Snapshot: ...
    def get_root(self, snapshot_id: str) -> Node: ...
    def get_node(self, inode: int) -> Node: ...
    def lookup(self, parent_inode: int, name: bytes) -> Node | None: ...
    def iter_children(self, parent_inode: int, offset: int = 0) -> Iterable[Node]: ...
```

The virtual mount root has `original_path=None`; every other node stores its
derived slash-joined path relative to that root. `Node.id` is also its FUSE
inode; the terms are interchangeable. An
`InMemorySnapshotBuilder` and `SQLiteSnapshotBuilder` share path validation,
parent synthesis, merge, conflict, and content-status rules. The import service
consumes the parser's single-pass iterator into an unpublished builder while the
source stream remains open. SQLite nodes are inserted incrementally rather than
accumulated as a second in-memory tree; set-based finalization assigns content
statuses. Parser diagnostics are final after the iterator is exhausted. If
parsing or validation fails, no store is returned, making partial snapshots
unobservable. Retained warnings and the total diagnostic count are frozen into
a successful store for inspection.

Each SQLite artifact contains exactly one snapshot and preserves root inode 1.
The version-4 schema requires SQLite `STRICT` tables and stores mounted names and
inline content as BLOBs, nullable content references and status, ISO 8601
timestamps, JSON metadata, and retained diagnostics. Metadata mappings and
arrays are recursively frozen in both backends and thawed for lossless JSON
serialization; pickle is never used. Foreign keys, sibling-name constraints,
lookup and traversal indexes, bytewise child ordering, an application
identifier, and a checked schema version protect the artifact.

Opening treats the database as untrusted. SQL checks storage classes and ranges
before Python touches BLOB values, and content type, length, and status without
loading content. Safe table-valued PRAGMA and bound `sqlite_master` queries
verify the exact required tables, column declarations and nullability, primary
keys, check constraints, foreign keys and actions, sibling unique constraints,
and named traversal indexes. A recursive CTE verifies every positive inode
reaches root 1; additional checks reject cycles, disconnected nodes,
non-directory parents, cross-snapshot nodes, invalid enums, invalid UTF-8,
non-root `.`/`..`, unsafe or oversized mounted names,
noncanonical virtual-root metadata, malformed diagnostics, and invalid
serialized values. Name and metadata validation is row-streamed. This bounds
validation memory independently of node count and content size.

Shared path normalization rejects any mounted component exceeding 255 UTF-8
bytes. Both builders therefore produce the same source-line `INVALID_PATH`
diagnostic, while SQLite open validation repeats the constraint for hostile or
externally modified artifacts. Prepublication validation errors are
recontextualized to the requested destination instead of exposing temporary
artifact names.

Persistent imports use a temporary database in the destination directory. Only
after parsing, builder validation, commit, close, file fsync, and a read-only
reopen check does publication atomically link a new output or replace an
existing one. No-overwrite hard-link publication is race-safe. It never unlinks
the destination to roll back a temporary-link cleanup failure, because another
writer may already have replaced that name. Explicit overwrite uses deliberate
atomic last-finisher-wins behavior; portable compare-and-swap replacement is not
available.

On hosts supporting directory file descriptors, the destination directory is
fsynced after the namespace operation. A failure is reported as
`SQLiteDurabilityError`, with the unavoidable caveat that the destination may
already have changed. Windows skips this unavailable durability operation. A
post-link temporary unlink failure is
reported as `SQLitePublicationError` and also leaves the published destination
alone. Before publication, failures and interrupts close the connection and
make a best-effort attempt to remove database, journal, WAL, and SHM files.
Cleanup errors cannot mask the initiating failure, but OS failures can leave an
unpublished temporary file. SQLite stores support idempotent `close()` and
context-manager use. An internal `RLock` serializes complete execute/fetch
operations and close; a close race either permits an already locked read to
finish or raises path-qualified `SQLiteStoreClosedError`.

## FUSE Semantics

The pyfuse3 adapter is read-only and implements `lookup`, `getattr`, directory
and file handle operations, `readdir`, `open`, `read`, and content-status
extended attributes. Mutating callbacks explicitly fail with `EROFS`.

- Inodes are stable for the lifetime of a mounted snapshot.
- Successful `lookup` replies and accepted `readdir` replies increment per-inode
  kernel lookup counts. Batched `forget` calls decrement without underflow;
  immutable nodes remain stored when counts reach zero.
- Directories use mode `0555`; files use mode `0444`.
- Mutating operations return `EROFS`.
- Opening a metadata-only file read-only is allowed; write-capable flags return
  `EROFS`.
- Reading missing content returns `ENODATA`, never fabricated empty bytes.
- Passing `--simulate-missing-content` changes missing-content reads to return
  NUL bytes up to the node's declared size. A read at offset `o` for length `n`
  returns `min(n, max(0, size - o))` zero bytes, so the adapter never allocates
  the full file unless requested. Attributes still report the declared size.
  Files with an unknown size still return `ENODATA`. Simulation applies only
  when `content is None` and `content_status=missing`; it does not mask remote,
  failed, or redacted states.
- A listed zero-length file has complete, provably empty content and is marked
  `present` with `content=b""`, so reading it returns EOF under either policy.
- `user.snapshotfs.content_status` exposes each node's content status.
- The adapter receives already-normalized nodes and contains no parser logic.

Initial-slice content invariants are:

- Directories have `size=None`, `content=None`, `content_ref=None`, and
  `content_status=not_applicable`.
- Metadata-only non-empty files have a declared size, `content=None`,
  `content_ref=None`, and `content_status=missing`.
- Zero-length files have `size=0`, `content=b""`, `content_ref=None`, and
  `content_status=present`.
- Inline content must have `len(content) == size` and `content_status=present`.
- Future externally stored content may be `present` with `content=None` and a
  verified `content_ref`; remote status also requires a reference.

Unit tests exercise the adapter directly without requiring a kernel mount.
Kernel-level mount tests are separate and skipped when `/dev/fuse`, libfuse 3,
or permissions are unavailable.

## CLI And Tooling

The project uses [uv](https://docs.astral.sh/uv/) for environments, dependency
resolution, lockfiles, commands, builds, and publishing. Common commands are:

```bash
uv sync --all-groups
uv sync --all-groups --extra fuse
uv run snapshotfs sqlite create backup.snapshot --source file listing.txt --parser windows-dir
uv run snapshotfs sqlite show backup.snapshot --json
uv run --extra fuse snapshotfs memory mount /tmp/snapshotfs --source file listing.txt --parser windows-dir
uv run --extra fuse snapshotfs sqlite mount backup.snapshot /tmp/snapshotfs
uv run pytest
uv run ruff check .
uv run mypy src
```

The Click CLI is organized by store type. A typed registry maps explicitly
selected source and parser names to factories and lets stores contribute a
top-level command group. SQLite owns `create`, `mount`, and `show`; memory owns
`mount`. A future HTTP store can therefore add its own configuration and
actions without changing root parser or dispatch code.

Commands that import a listing identify the explicit source and parser, then
install parameters from only that pair. Registrations own all construction
syntax; the built-in `file` registration defines its input positional and
`windows-dir` defines encoding and date-format options. Required arguments on
unselected components therefore do not apply, and unrelated registrations may
reuse option names. Duplicate names and conflicts between the selected pair
fail clearly.

Registry names provide source and parser choices and completions. Selected
component flags and values are available after an exact selector is present.
`main` and command construction accept an injected registry for embedding and
tests. Users enable Bash, Zsh, or Fish completion with
`eval "$(snapshotfs completion SHELL)"`.

`sqlite create` creates an artifact and can mount it immediately with `--mount`.
`sqlite show` and `sqlite mount` consume an existing artifact without source or
parser selection. All CLI paths close SQLite stores on normal return, mount
failure, and interruption. `memory mount` creates a transient store from
registry-created components, passes it to `snapshotfs.api.mount_store`, and
runs until interrupted.
pyfuse3 and Trio are Linux-only dependencies in the optional `fuse` extra;
pyfuse3 requires system libfuse 3 development headers to build. Parsing and
import tests remain runnable without pyfuse3, including on Windows and macOS,
because the CLI imports the FUSE adapter only for `mount`.

## Library API

The package exports the source and parser protocols, built-in implementations,
explicit store creators, and `mount_store`. pyfuse3 remains lazily imported:

```python
from snapshotfs import (
    FileSource,
    WindowsDirParser,
    create_memory_store,
    create_sqlite_store,
    mount_store,
    open_sqlite_store,
)

source = FileSource("listing.txt")
parser = WindowsDirParser(encoding="cp1252", date_format="mdy")

store = create_memory_store(source, parser)
mount_store(store, "/mnt/snapshot", simulate_missing_content=False)

with create_sqlite_store(source, parser, "snapshot.db") as persisted:
    print(list(persisted.iter_nodes()))
with open_sqlite_store("snapshot.db") as persisted:
    mount_store(persisted, "/mnt/snapshot")
```

`mount_store(store, mountpoint, ...)` mounts an already imported store when the
caller does not want to import the source a second time.

## Security And Robustness

- Treat all input as untrusted.
- Limit a physical line to 1 MiB and retained diagnostics to 1,000.
- Never resolve imported Windows paths against the host filesystem.
- Reject NUL and mounted names containing `/`.
- Avoid catastrophic regular expressions and unbounded backtracking.
- Keep file content unavailable unless inline bytes or a verified content
  reference exists. Exceptions are a listed zero-length file, whose content is
  known without a reference, and explicitly requested simulation, which is
  visibly configured stand-in data rather than original content.
- Do not execute text found in listings.
- Bound future remote reads, redirects, retries, and cache sizes.

## Deferred Work

- SQLite schema migrations beyond rejecting unsupported versions.
- File content ingestion and content-addressed storage.
- HTTP and object-storage sources.
- Format auto-detection and installed-package plugin discovery. Programmatic
  store command registration is supported.
- Localized Windows `dir /s`, GNU `ls -R`, and other listing formats.
- UNC paths, alternate data streams, junctions, and reparse points.
- Snapshot comparison and writable overlays.
