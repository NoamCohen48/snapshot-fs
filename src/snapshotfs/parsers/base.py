from collections.abc import Iterator
from typing import BinaryIO, Protocol

from snapshotfs.diagnostics import DiagnosticCollector, ImportDiagnostic
from snapshotfs.model import ParsedEntry


class ParseResult:
    """A single-pass entry stream with diagnostics populated during consumption."""

    def __init__(
        self, entries: Iterator[ParsedEntry], diagnostics: DiagnosticCollector
    ) -> None:
        self.entries = entries
        self._diagnostics = diagnostics

    @property
    def diagnostics(self) -> tuple[ImportDiagnostic, ...]:
        return self._diagnostics.items

    @property
    def diagnostic_count(self) -> int:
        return self._diagnostics.total

    @property
    def has_errors(self) -> bool:
        return self._diagnostics.has_errors


class Parser(Protocol):
    format_name: str

    def parse(self, stream: BinaryIO) -> ParseResult: ...
