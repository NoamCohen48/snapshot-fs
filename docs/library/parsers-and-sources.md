# Sources And Parsers

[Python library](index.md)

## Sources

A `Source` supplies a binary stream and provenance. It does not choose an
encoding or interpret data.

```python
from snapshotfs import FileSource

source = FileSource("listing.txt")
print(source.uri)
print(source.size)

with source.open() as stream:
    prefix = stream.read(16)
```

`FileSource` uses an absolute `file:` URI, opens in binary mode, and wraps file
inspection or opening failures in `SourceError`.

## Parsers

A `Parser` consumes a binary stream and returns a lazy, single-pass
`ParseResult`. Diagnostics are populated as entries are consumed:

```python
from snapshotfs import FileSource, WindowsDirParser

source = FileSource("listing.txt")
parser = WindowsDirParser(encoding="cp1252", date_format="dmy")

with source.open() as stream:
    result = parser.parse(stream)
    entries = tuple(result.entries)

print(result.diagnostic_count, result.has_errors)
```

Inspecting diagnostics before consuming `result.entries` may produce incomplete
results. Use `create_memory_store()` or `create_sqlite_store()` for normal
fail-closed imports.

## Windows Directory Listings

`WindowsDirParser` supports a deliberately restricted English `dir /s` dialect:

- absolute drive-letter paths;
- four-digit years and `mdy`, `dmy`, or `ymd` date ordering;
- 12-hour or 24-hour times;
- `<DIR>` entries and numeric file sizes;
- complete section and aggregate summaries.

Localized labels, UNC paths, alternate data streams, two-digit years, unsafe
components, and malformed or reordered summaries are rejected. Decoding is
strict and SnapshotFS performs no encoding detection.
