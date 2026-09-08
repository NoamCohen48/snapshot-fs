from collections.abc import Iterable
from typing import Protocol

from snapshotfs.diagnostics import ImportDiagnostic
from snapshotfs.model import Node, Snapshot


class ImportFailure(ValueError):
    """An import failed validation and did not publish a store."""

    def __init__(
        self,
        diagnostics: tuple[ImportDiagnostic, ...],
        diagnostic_count: int | None = None,
    ) -> None:
        self.diagnostics = diagnostics
        self.diagnostic_count = (
            diagnostic_count if diagnostic_count is not None else len(diagnostics)
        )
        super().__init__(diagnostics[0].message if diagnostics else "import failed")


class SnapshotStore(Protocol):
    @property
    def diagnostics(self) -> tuple[ImportDiagnostic, ...]: ...

    @property
    def diagnostic_count(self) -> int: ...

    def get_snapshot(self, snapshot_id: str) -> Snapshot: ...

    def get_root(self, snapshot_id: str) -> Node: ...

    def get_node(self, inode: int) -> Node: ...

    def lookup(self, parent_inode: int, name: bytes) -> Node | None: ...

    def iter_children(self, parent_inode: int, offset: int = 0) -> Iterable[Node]: ...

    def iter_nodes(self) -> Iterable[Node]: ...
