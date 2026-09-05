"""Read-only SQLite snapshot store."""

import sqlite3
from collections.abc import Iterable
from pathlib import Path
from threading import RLock
from typing import cast

from snapshotfs.diagnostics import ImportDiagnostic, Severity
from snapshotfs.model import ContentStatus, Node, NodeKind, Snapshot
from snapshotfs.stores.sqlite.codec import decode_datetime, decode_metadata
from snapshotfs.stores.sqlite.contract import validate_schema_contract
from snapshotfs.stores.sqlite.errors import (
    SQLiteSchemaError,
    SQLiteStoreClosedError,
    SQLiteStoreError,
)
from snapshotfs.stores.sqlite.schema import APPLICATION_ID, SCHEMA_VERSION, configure
from snapshotfs.stores.sqlite.validation import validate_records


class SQLiteSnapshotStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = RLock()
        self._connection: sqlite3.Connection | None = None
        if not self.path.exists():
            raise SQLiteStoreError(self.path, "snapshot artifact does not exist")
        if not self.path.is_file():
            raise SQLiteStoreError(self.path, "snapshot artifact is not a regular file")
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                f"{self.path.resolve().as_uri()}?mode=ro",
                uri=True,
                check_same_thread=False,
            )
            connection.row_factory = sqlite3.Row
            configure(connection)
            self._validate(connection)
        except SQLiteStoreError:
            if connection is not None:
                connection.close()
            raise
        except (sqlite3.Error, ValueError, KeyError) as exc:
            if connection is not None:
                connection.close()
            raise SQLiteSchemaError(
                self.path, f"invalid SQLite artifact: {exc}"
            ) from exc
        assert connection is not None
        self._connection = connection

    def __enter__(self) -> "SQLiteSnapshotStore":
        with self._lock:
            self._require_open()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    @property
    def diagnostics(self) -> tuple[ImportDiagnostic, ...]:
        rows = self._query_all(
            "SELECT severity, code, message, line_number "
            "FROM diagnostics ORDER BY position"
        )
        try:
            return tuple(
                ImportDiagnostic(Severity(row[0]), row[1], row[2], row[3])
                for row in rows
            )
        except (TypeError, ValueError) as exc:
            raise SQLiteSchemaError(
                self.path, f"invalid diagnostic record: {exc}"
            ) from exc

    @property
    def diagnostic_count(self) -> int:
        row = self._query_one("SELECT diagnostic_count FROM snapshot")
        assert row is not None
        if not isinstance(row[0], int) or isinstance(row[0], bool) or row[0] < 0:
            raise SQLiteSchemaError(self.path, "invalid diagnostic count")
        return row[0]

    def get_snapshot(self, snapshot_id: str) -> Snapshot:
        row = self._query_one(
            "SELECT id, source_uri, source_format, imported_at, metadata_json "
            "FROM snapshot WHERE id = ?",
            (snapshot_id,),
        )
        if row is None:
            raise KeyError(snapshot_id)
        try:
            imported_at = decode_datetime(row[3])
            if imported_at is None:
                raise ValueError("imported_at must not be null")
            return Snapshot(
                row[0], row[1], row[2], imported_at, decode_metadata(row[4])
            )
        except (ValueError, TypeError) as exc:
            raise SQLiteSchemaError(
                self.path, f"invalid snapshot record: {exc}"
            ) from exc

    def get_root(self, snapshot_id: str) -> Node:
        self.get_snapshot(snapshot_id)
        return self.get_node(1)

    def get_node(self, inode: int) -> Node:
        row = self._query_one("SELECT * FROM nodes WHERE id = ?", (inode,))
        if row is None:
            raise KeyError(inode)
        return self._node(row)

    def lookup(self, parent_inode: int, name: bytes) -> Node | None:
        self.get_node(parent_inode)
        row = self._query_one(
            "SELECT * FROM nodes WHERE parent_id = ? AND mounted_name = ?",
            (parent_inode, name),
        )
        return self._node(row) if row is not None else None

    def iter_children(self, parent_inode: int, offset: int = 0) -> Iterable[Node]:
        self.get_node(parent_inode)
        row = self._query_one(
            "SELECT COUNT(*) FROM nodes WHERE parent_id = ?", (parent_inode,)
        )
        assert row is not None
        count = row[0]
        assert isinstance(count, int)
        if offset < 0:
            offset = max(0, count + offset)
        elif offset >= count:
            return ()
        rows = self._query_all(
            "SELECT * FROM nodes WHERE parent_id = ? "
            "ORDER BY mounted_name COLLATE BINARY LIMIT -1 OFFSET ?",
            (parent_inode, offset),
        )
        return tuple(self._node(row) for row in rows)

    def iter_nodes(self) -> Iterable[Node]:
        return tuple(
            self._node(row)
            for row in self._query_all("SELECT * FROM nodes ORDER BY id")
        )

    def _require_open(self) -> sqlite3.Connection:
        if self._connection is None:
            raise SQLiteStoreClosedError(self.path, "snapshot store is closed")
        return self._connection

    def _query_one(
        self, sql: str, parameters: tuple[object, ...] = ()
    ) -> sqlite3.Row | None:
        with self._lock:
            try:
                return cast(
                    sqlite3.Row | None,
                    self._require_open().execute(sql, parameters).fetchone(),
                )
            except sqlite3.Error as exc:
                if self._connection is None:
                    raise SQLiteStoreClosedError(
                        self.path, "snapshot store is closed"
                    ) from exc
                raise SQLiteSchemaError(
                    self.path, f"cannot read artifact: {exc}"
                ) from exc

    def _query_all(
        self, sql: str, parameters: tuple[object, ...] = ()
    ) -> list[sqlite3.Row]:
        with self._lock:
            try:
                return self._require_open().execute(sql, parameters).fetchall()
            except sqlite3.Error as exc:
                if self._connection is None:
                    raise SQLiteStoreClosedError(
                        self.path, "snapshot store is closed"
                    ) from exc
                raise SQLiteSchemaError(
                    self.path, f"cannot read artifact: {exc}"
                ) from exc

    def _node(self, row: sqlite3.Row) -> Node:
        try:
            mounted_name = row["mounted_name"]
            content = row["content"]
            if not isinstance(mounted_name, bytes):
                raise TypeError("mounted_name is not a BLOB")
            if content is not None and not isinstance(content, bytes):
                raise TypeError("content is not a BLOB")
            metadata = decode_metadata(row["metadata_json"])
            return Node(
                row["id"],
                row["snapshot_id"],
                row["parent_id"],
                mounted_name,
                row["original_path"],
                NodeKind(row["kind"]),
                row["size"],
                decode_datetime(row["modified_at"]),
                content,
                ContentStatus(row["content_status"]),
                row["content_ref"],
                row["source_line"],
                metadata,
            )
        except (ValueError, TypeError, KeyError) as exc:
            raise SQLiteSchemaError(self.path, f"invalid node record: {exc}") from exc

    def _validate(self, connection: sqlite3.Connection) -> None:
        application_id = int(connection.execute("PRAGMA application_id").fetchone()[0])
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if application_id != APPLICATION_ID:
            raise SQLiteSchemaError(self.path, "file is not a SnapshotFS artifact")
        if version != SCHEMA_VERSION:
            raise SQLiteSchemaError(
                self.path,
                f"unsupported schema version {version}; expected {SCHEMA_VERSION}",
            )
        integrity = connection.execute("PRAGMA quick_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise SQLiteSchemaError(self.path, "SQLite integrity check failed")
        validate_schema_contract(connection, self.path)
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise SQLiteSchemaError(self.path, "artifact has invalid foreign keys")
        snapshot_count = int(
            connection.execute("SELECT COUNT(*) FROM snapshot").fetchone()[0]
        )
        top_level_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM nodes WHERE parent_id IS NULL"
            ).fetchone()[0]
        )
        root = connection.execute(
            "SELECT id, parent_id, kind FROM nodes WHERE id = 1"
        ).fetchone()
        if snapshot_count != 1 or root is None or top_level_count != 1:
            raise SQLiteSchemaError(
                self.path, "artifact must contain one snapshot and root"
            )
        validate_records(connection, self.path)
        if root[1] is not None or root[2] != "directory":
            raise SQLiteSchemaError(self.path, "inode 1 is not a valid root directory")
        counts = connection.execute(
            "SELECT diagnostic_count, (SELECT COUNT(*) FROM diagnostics) FROM snapshot"
        ).fetchone()
        assert counts is not None
        if int(counts[0]) < int(counts[1]):
            raise SQLiteSchemaError(
                self.path, "diagnostic count is smaller than retained diagnostics"
            )


def open_sqlite_store(path: str | Path) -> SQLiteSnapshotStore:
    return SQLiteSnapshotStore(path)
