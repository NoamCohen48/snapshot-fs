# SnapshotFS Implementation Plan

## Goal Of The First Slice

Build a tested Python package that reads an English Windows `dir /s` listing
from a local file and produces a validated, normalized in-memory snapshot. Add
an inspection CLI that prints the normalized tree and diagnostics. Define the
store and FUSE boundaries, but do not require FUSE to run the parser or tests.

The completed implementation also includes the read-only Linux mount slice and
single-snapshot SQLite artifacts.

## Acceptance Criteria

- The project is managed with `uv` and has a committed `uv.lock`.
- The package uses a `src/` layout and supports Python 3.12 or newer.
- `FileSource` streams bytes from a local file and reports contextual errors.
- Decoding supports UTF-8, a UTF-8 BOM, UTF-16, ASCII, Latin-1, and explicit
  Windows-125x encodings such as cp1252. Stateful or buffering codecs are
  rejected before input is consumed.
- The parser handles native Windows `dir /s` with English structural labels,
  files, directories, spaces in names, comma-separated sizes, `File Not Found`,
  aggregate footers, and empty directories.
- Date ordering is explicit (`mdy`, `dmy`, or `ymd`); four-digit years and 12-
  and 24-hour times are supported, while ambiguous two-digit years are rejected.
- Drive-letter paths normalize below a drive node such as `C/`.
- Missing parent directories are synthesized deterministically.
- Exact duplicate entries merge; type and metadata collisions
  representing incompatible entries, or metadata conflicts fail clearly.
- A complete aggregate footer is required, and file counts and byte totals are
  validated for every section and the complete listing.
- Unsupported or malformed meaningful lines include line-numbered diagnostics.
- Snapshot publication is atomic from the caller's perspective.
- `snapshotfs sqlite show` can emit a human-readable tree and JSON.
- CLI calls require explicit `--source file` and `--parser windows-dir`; no
  probing or automatic detection is performed.
- Click provides Bash, Zsh, and Fish completion for commands, flags, paths, and
  the explicit source/parser choices.
- On Linux with the `fuse` extra, `snapshotfs memory mount` exposes the imported
  in-memory tree as a read-only filesystem until interrupted.
- Listing files have nullable content; zero-length files normalize to `b""` and
  non-empty metadata-only files normalize to `None`.
- Directories use `content_status=not_applicable`; simulation is eligible only
  for `content=None`, `content_status=missing`, and a known declared size.
- Runtime parser imports do not require pyfuse3 or system libfuse headers.
- Library callers can compose `Source` and `Parser` objects with
  `create_memory_store`, `create_sqlite_store`, or `mount_store`.
- `create_sqlite_store` streams entries to a temporary sibling database and
  atomically publishes only a committed, validated artifact; `open_sqlite_store`
  reopens it with explicit close and context-manager lifecycle support.
- SQLite artifacts preserve inode 1, diagnostics, BLOB content and names, and
  JSON metadata, and reject existing destinations unless overwrite is explicit.
- Unit tests cover happy paths, malformed input, encodings, conflicts, and path
  safety.
- `uv run pytest`, `uv run ruff check .`, and `uv run mypy src` pass.

## Package Layout

```text
pyproject.toml
uv.lock
src/snapshotfs/
  __init__.py
  cli.py
  cli_output.py
  diagnostics.py
  import_service.py
  decoding.py
  model/
    __init__.py
    enums.py
    metadata.py
    node.py
    parsed_entry.py
    snapshot.py
  sources/
    __init__.py
    base.py
    file.py
  parsers/
    __init__.py
    base.py
    windows_dir/
      __init__.py
      grammar.py
      parser.py
      state.py
  stores/
    __init__.py
    base.py
    memory/
      __init__.py
      builder.py
      errors.py
      paths.py
      store.py
    sqlite/
      __init__.py
      artifact.py
      builder.py
      codec.py
      contract.py
      errors.py
      schema.py
      store.py
      validation.py
  fuse/
    __init__.py
    policy.py
    adapter/
      __init__.py
      mount.py
      operations.py
      read_only.py
tests/
  fixtures/
  test_cli.py
  test_file_source.py
  test_windows_dir_parser.py
  test_import_service.py
docs/
  architecture.md
  implementation-plan.md
```

## Work Sequence

1. Initialize the package with `uv`, Python 3.12, pytest, Ruff, and mypy.
2. Add immutable domain models for nodes, snapshots, and diagnostics.
3. Define source, parser, and store protocols without importing FUSE.
4. Implement `FileSource` and strict incremental text decoding.
5. Implement the English Windows `dir /s` state-machine parser.
6. Implement path normalization and the atomic in-memory snapshot builder.
7. Implement `snapshotfs sqlite show` with tree and JSON output.
8. Add focused fixtures and unit tests for all acceptance criteria.
9. Run formatting, linting, typing, and tests through `uv`.
10. Perform an independent code review and repeat fixes and review until the
   reviewer reports no blocking findings.

## Parser State Machine

The parser accepts bytes and uses the shared strict line decoder. It tracks
whether it is before the first section, inside a directory section, or inside
the aggregate footer. It classifies each decoded line in this order:

1. Blank line.
2. Volume banner or serial-number banner.
3. `Directory of` section header.
4. File or directory entry while inside a section.
5. `File Not Found` empty-section marker.
6. Per-section file or directory summary.
7. `Total Files Listed:` and aggregate summaries, with validated file counts
   and byte totals.
8. EOF, accepted only after a complete aggregate footer.
9. Unknown meaningful line, which becomes an error diagnostic.

Section records are ordered: entries or one `File Not Found` marker, then the
`File(s)` summary, then the `Dir(s)` summary. `File Not Found` cannot be mixed
with entries, and entries after either summary are errors. Aggregate summaries
are ordered `File(s)` then `Dir(s)`.

Regular expressions only identify fixed prefixes and timestamp/size fields.
After the native marker delimiter, the filename is the unparsed remainder so
leading spaces are preserved. Parsing is line-oriented and entries are consumed
directly into the unpublished builder while the source is open, so parser memory
does not grow with entry count.

## Normalization Decisions

- Parsers emit a tuple of mounted path components relative to the virtual root.
  Stores do not infer source separators, roots, drives, or case behavior.
- `C:\Users\Alice` becomes mounted components `C`, `Users`, `Alice`.
- Drive letters are normalized to uppercase.
- Windows `.` and `..` entries are ignored; traversal in section paths is
  rejected by the Windows parser.
- Relative section paths, NUL, `/`, repeated or trailing empty non-root
  components, and alternate-data-stream colons are rejected before path-library
  normalization. Entry names containing `:`, `/`, or `\` are rejected.
- Generic mounted components reject empty names, `.`, `..`, NUL, `/`, and names
  over 255 UTF-8 bytes. Other source-format restrictions belong to parsers.
- Directory nodes are synthesized from the virtual root downward.
- Relative mounted paths and optional source line numbers are retained.
- Every section header emits a directory `ParsedEntry` observation, including
  for empty sections. A later explicit entry enriches a synthesized or
  header-only directory.
- Mounted names are UTF-8 bytes. Paths and lookup are exact and case-sensitive;
  directory ordering is bytewise.
- Incompatible entries at the same exact relative path are rejected.

## Error Policy

Structural uncertainty fails closed. A listing that cannot be interpreted
reliably does not produce a partial successful snapshot.

- Source failures raise typed source exceptions.
- Decode failures identify byte offset and requested encoding.
- Parse failures accumulate stable diagnostic codes and source line numbers up
  to 1,000 retained diagnostics; any error prevents a store from being returned.
  If normalization fails after that retained set is full, its conflict
  diagnostic replaces a retained warning (or the last retained item) so source
  line details remain visible without increasing the bound.
- Conflicts identify the existing and incoming entries.
- CLI errors go to stderr and return a non-zero status.
- Successful warnings and the total diagnostic count are retained by the store
  and shown by both inspection output formats.

Warnings are reserved for information that does not change the reconstructed
tree. A physical line over 1 MiB is a fatal decode error. The CLI displays at
most the retained 1,000 diagnostics and reports the total observed count.

## Test Matrix

| Area | Cases |
| --- | --- |
| File source | Existing file, missing file, directory passed as file, permission error where supported, chunked reads. |
| Decode | UTF-8, UTF-8 BOM, CRLF, cp1252 with explicit option, invalid and incomplete bytes, multibyte byte limits. |
| Headers | Drive root, nested directory, spaces, mixed drive-letter case, malformed and relative paths. |
| Entries | File, directory, zero-byte file, comma size, leading spaces, dot entries, ordered summaries, exclusive `File Not Found`, empty directory. |
| Footers | Per-section summaries, `Total Files Listed:`, aggregate summaries. |
| Completeness | Missing aggregate footer, premature EOF, per-section mismatch, aggregate count mismatch, aggregate byte mismatch. |
| Metadata | MDY/DMY/YMD, separators, rejected two-digit year, AM, PM, 24-hour, noon, midnight, invalid date, invalid size, timezone-free JSON. |
| Tree building | Section-only empty directory, synthesized parent enrichment, exact duplicate merge, case-distinct names, file-directory conflict, duplicate metadata conflict. |
| Safety | NUL, slash, backslash, colon/ADS, repeated empty path components, parent traversal, oversized line. |
| CLI | Tree output, JSON output, retained warnings, encoding option, memory and SQLite import/mount options, store closure, completion, error status and stderr. |
| SQLite | Memory parity, deep metadata immutability, reopen, Unicode, BLOB content, diagnostics, huge offsets, conflicts, JSON rejection, strict storage classes, malicious graph/domain records, race-safe publication, last-finisher overwrite, fsync and cleanup faults, concurrent read/close, schema/corruption/missing errors, and memory/SQLite FUSE coverage. |
| Read policy | Inline slices, missing `ENODATA`, bounded simulation, EOF, unknown and non-missing statuses. |
| FUSE adapter | Attributes, lookup errors, handles, deterministic offsets, open/read, xattrs, and `EROFS` mutations. |

## Review Gates

Documentation gate:

- An independent reviewer checks architecture boundaries, parser assumptions,
  FUSE semantics, scope, acceptance criteria, and testability.
- Findings are corrected and resubmitted until the reviewer explicitly
  approves the plan with no blocking findings.

Implementation gate:

- A separate implementation agent builds the approved first slice.
- An independent reviewer prioritizes correctness, security, behavioral gaps,
  and missing tests.
- All blocking findings are fixed and reviewed again until approval.
- The final local verification runs all locked `uv` quality commands.

## Read-Only Mount Slice

The Linux mount slice is implemented with pyfuse3 and Trio in the optional
`fuse` extra. `snapshotfs memory mount` imports a listing into the immutable in-memory
store and mounts it until interrupted. The adapter provides stable attributes,
deterministic directory offsets, exact mounted-name lookup, handle validation,
content-status xattrs, explicit `EROFS` mutations, default `ENODATA` reads, and
opt-in bounded missing-content simulation. Pure policy tests run without FUSE;
adapter tests run directly when the extra and system library are available.

## SQLite Persistence Slice

`snapshotfs sqlite create OUTPUT --source ... --parser ...` and
`create_sqlite_store` streams normalized nodes into an unpublished sibling
database. Shared normalization and merge logic keeps the memory and SQLite
builders behaviorally aligned. Finalization uses SQL updates rather than loading
the tree, commits and closes the database, validates a read-only reopen, then
atomically publishes. Version-4 artifacts require strict tables and validate
storage classes, ranges, graph reachability, FUSE names/inodes, enums, content,
diagnostics, and JSON before exposure. No-overwrite publication is race-safe;
explicit overwrite is atomic last-finisher-wins. Directory durability and
post-link cleanup failures report typed errors noting that publication may
already have occurred. Pre-publication cleanup is best effort and never masks
the original failure. `sqlite show`, `sqlite mount`, and `open_sqlite_store`
reopen one-snapshot artifacts with synchronized read/close behavior and root
inode 1.
