# Parser

[Development](../README.md) / Parser

A parser owns an input format. It consumes a source's binary stream, produces
normalized `ParsedEntry` values, and reports structured diagnostics.

## Contract

Implement the `Parser` protocol from `snapshotfs.parsers.base`:

```python
class Parser(Protocol):
    format_name: str

    def parse(self, stream: BinaryIO) -> ParseResult: ...
```

`ParseResult.entries` is a single-pass iterator. Diagnostics are accumulated as
the import service consumes that iterator, so parsers can process large inputs
without creating a complete intermediate tree.

## Responsibilities

- Decode text formats from the binary stream when required.
- Assign `ParsedEntry.path` as components relative to the virtual mount root.
- Preserve source location information in entries and diagnostics.
- Detect format-specific structural errors and continue collecting diagnostics
  when it is safe to do so.

Parsers must not assign inode numbers, build stores, mount filesystems, or
interpret paths using the host operating system. Builders validate mounted-name
safety and create missing parent nodes.

## Testing

Cover valid input, malformed structure, invalid encoding when applicable,
diagnostic locations, duplicate entries, and paths at the format boundary. Test
the parser through the import service as well as at the parser boundary so the
single-pass diagnostic behavior is exercised.
