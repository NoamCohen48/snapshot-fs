"""Import orchestration with all-or-nothing publication."""

from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from snapshotfs.diagnostics import MAX_DIAGNOSTICS, ImportDiagnostic, Severity
from snapshotfs.model import ParsedEntry, Snapshot
from snapshotfs.parser import Parser
from snapshotfs.source import Source
from snapshotfs.store.base import ImportFailure
from snapshotfs.store.building import BuildError


class SnapshotBuilder[StoreT](Protocol):
    def add(self, entry: ParsedEntry) -> None: ...

    def finish(
        self,
        diagnostics: tuple[ImportDiagnostic, ...] = (),
        diagnostic_count: int | None = None,
    ) -> StoreT: ...

    def abort(self) -> None: ...


def _create_store[StoreT](
    source: Source,
    parser: Parser,
    builder_factory: Callable[[Snapshot], SnapshotBuilder[StoreT]],
) -> StoreT:
    snapshot = Snapshot(
        str(uuid4()),
        source.uri,
        parser.format_name,
        datetime.now(UTC),
    )
    builder = builder_factory(snapshot)
    build_diagnostic: ImportDiagnostic | None = None
    try:
        with source.open() as stream:
            result = parser.parse(stream)
            for entry in result.entries:
                if build_diagnostic is None:
                    try:
                        builder.add(entry)
                    except BuildError as exc:
                        build_diagnostic = exc.diagnostic

        diagnostics = result.diagnostics
        diagnostic_count = result.diagnostic_count
        if build_diagnostic is not None:
            diagnostic_count += 1
            if len(diagnostics) < MAX_DIAGNOSTICS:
                diagnostics += (build_diagnostic,)
            else:
                replacement = next(
                    (
                        index
                        for index in range(len(diagnostics) - 1, -1, -1)
                        if diagnostics[index].severity is Severity.WARNING
                    ),
                    len(diagnostics) - 1,
                )
                diagnostics = (
                    *diagnostics[:replacement],
                    build_diagnostic,
                    *diagnostics[replacement + 1 :],
                )
        if result.has_errors or build_diagnostic is not None:
            raise ImportFailure(diagnostics, diagnostic_count)
        return builder.finish(diagnostics, diagnostic_count)
    except BaseException:
        with suppress(Exception):
            builder.abort()
        raise
