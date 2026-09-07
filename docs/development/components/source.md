# Source

[Development](../README.md) / Source

A source obtains raw input bytes and describes where they came from. It does
not decode text or interpret listing syntax.

## Contract

Implement the `Source` protocol from `snapshotfs.sources.base`:

```python
class Source(Protocol):
    @property
    def uri(self) -> str: ...

    @property
    def size(self) -> int | None: ...

    def open(self) -> AbstractContextManager[BinaryIO]: ...
```

`uri` is recorded in the imported snapshot. `size` is optional because some
sources cannot know their length before reading. `open()` must provide a binary
stream through a context manager so the import service can control its lifetime.

## Implementation Guidance

- Keep transport, authentication, and source-specific errors inside the source.
- Return bytes exactly as acquired; decoding belongs to a parser.
- Avoid loading the complete input into memory when the transport can stream.
- Add a CLI registration only when the source should be user-selectable from the
  command line.

Test successful reads and source-specific failures, including cleanup of any
resources opened by the source.
