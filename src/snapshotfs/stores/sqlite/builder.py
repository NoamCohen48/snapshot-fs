"""Streaming SQLite builder with atomic artifact publication."""

import sqlite3
from contextlib import suppress
from pathlib import Path

from snapshotfs.diagnostics import ImportDiagnostic
from snapshotfs.model import ContentStatus, NodeKind, Observation, ParsedEntry, Snapshot
from snapshotfs.stores.building import (
    MutableNode,
    components,
    conflict,
    entry_location,
    merge,
)
from snapshotfs.stores.sqlite.artifact import cleanup, create_temporary, publish
from snapshotfs.stores.sqlite.codec import (
    decode_datetime,
    decode_metadata,
    encode_datetime,
    encode_metadata,
)
from snapshotfs.stores.sqlite.errors import (
    SQLiteDestinationExistsError,
    SQLitePersistenceError,
    SQLiteSchemaError,
)
from snapshotfs.stores.sqlite.schema import configure, create_schema
from snapshotfs.stores.sqlite.store import SQLiteSnapshotStore


class SQLiteSnapshotBuilder:
    def __init__(
        self, snapshot: Snapshot, destination: str | Path, *, overwrite: bool = False
    ) -> None:
        self.destination = Path(destination)
        self._overwrite = overwrite
        self._finished = False
        self._temporary: Path | None = None
        self._connection: sqlite3.Connection | None = None
        self._next_inode = 2
        if self.destination.exists() and not overwrite:
            raise SQLiteDestinationExistsError(
                self.destination, "destination already exists (use overwrite=True)"
            )
        if not self.destination.parent.is_dir():
            raise SQLitePersistenceError(
                self.destination, "parent directory does not exist"
            )
        self._temporary = create_temporary(self.destination)
        try:
            self._connection = sqlite3.connect(self._temporary)
            configure(self._connection)
            create_schema(self._connection)
            self._insert_snapshot(snapshot)
            self._insert_node(
                snapshot.id,
                MutableNode(1, None, b"", None, NodeKind.DIRECTORY),
            )
        except SQLitePersistenceError:
            self.abort()
            raise
        except (OSError, sqlite3.Error) as exc:
            self.abort()
            raise SQLitePersistenceError(
                self.destination, f"cannot initialize artifact: {exc}"
            ) from exc
        except BaseException:
            self.abort()
            raise
        self._snapshot = snapshot

    def add(self, entry: ParsedEntry) -> None:
        try:
            encode_metadata(entry.source_metadata)
        except (TypeError, ValueError) as exc:
            raise SQLitePersistenceError(
                self.destination,
                f"entry metadata at {entry_location(entry)} is not JSON "
                f"serializable: {exc}",
            ) from exc
        try:
            self._add_entry(entry)
        except sqlite3.Error as exc:
            raise SQLitePersistenceError(
                self.destination,
                f"cannot persist entry at {entry_location(entry)}: {exc}",
            ) from exc

    def _add_entry(self, entry: ParsedEntry) -> None:
        connection = self._active()
        parent_id = 1
        path_components = components(entry)
        for index, mounted_name in enumerate(path_components):
            final = index == len(path_components) - 1
            kind = entry.kind if final else NodeKind.DIRECTORY
            row = connection.execute(
                "SELECT * FROM nodes WHERE parent_id = ? AND mounted_name = ?",
                (parent_id, mounted_name),
            ).fetchone()
            if row is None:
                node = MutableNode(
                    self._next_inode,
                    parent_id,
                    mounted_name,
                    "/".join(entry.path[: index + 1]),
                    kind,
                )
                self._next_inode += 1
                self._insert_node(self._snapshot.id, node)
            else:
                node = self._mutable(row)
                if node.kind is not kind:
                    conflict(node, entry, "file/directory type conflict")
            if final:
                merge(node, entry)
                self._update_node(node, encode_metadata(node.source_metadata))
            parent_id = node.id

    def finish(
        self,
        diagnostics: tuple[ImportDiagnostic, ...] = (),
        diagnostic_count: int | None = None,
    ) -> SQLiteSnapshotStore:
        connection = self._active()
        try:
            connection.execute(
                "UPDATE nodes SET content = X'' "
                "WHERE kind = 'file' AND size = 0 AND content IS NULL"
            )
            connection.execute(
                "UPDATE nodes SET content_status = CASE "
                "WHEN kind = 'directory' THEN 'not_applicable' "
                "WHEN kind = 'file' AND content IS NOT NULL THEN 'present' "
                "ELSE 'missing' END"
            )
            connection.executemany(
                "INSERT INTO diagnostics VALUES (?, ?, ?, ?, ?)",
                [
                    (
                        index,
                        item.severity.value,
                        item.code,
                        item.message,
                        item.line_number,
                    )
                    for index, item in enumerate(diagnostics)
                ],
            )
            connection.execute(
                "UPDATE snapshot SET diagnostic_count = ?",
                (
                    diagnostic_count
                    if diagnostic_count is not None
                    else len(diagnostics),
                ),
            )
            foreign_key_error = connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchone()
            if foreign_key_error is not None:
                raise SQLitePersistenceError(
                    self.destination, "artifact failed foreign-key validation"
                )
            connection.commit()
            self._close_connection()
            temporary = self._temporary
            assert temporary is not None
            with SQLiteSnapshotStore(temporary):
                pass
            publish(temporary, self.destination, overwrite=self._overwrite)
            self._temporary = None
            self._finished = True
            return SQLiteSnapshotStore(self.destination)
        except SQLitePersistenceError:
            self.abort()
            raise
        except SQLiteSchemaError as exc:
            self.abort()
            raise SQLiteSchemaError(
                self.destination,
                f"built artifact failed validation: {exc.detail}",
            ) from exc
        except (OSError, sqlite3.Error) as exc:
            self.abort()
            raise SQLitePersistenceError(
                self.destination, f"cannot finalize artifact: {exc}"
            ) from exc
        except BaseException:
            self.abort()
            raise

    def abort(self) -> None:
        connection = self._connection
        self._connection = None
        if connection is not None:
            with suppress(sqlite3.Error):
                connection.close()
        self._cleanup_temporary()
        self._finished = True

    def _insert_snapshot(self, snapshot: Snapshot) -> None:
        try:
            metadata = encode_metadata(snapshot.source_metadata)
        except (TypeError, ValueError) as exc:
            raise SQLitePersistenceError(
                self.destination, f"snapshot metadata is not JSON serializable: {exc}"
            ) from exc
        self._active().execute(
            "INSERT INTO snapshot VALUES (?, ?, ?, ?, ?, 0)",
            (
                snapshot.id,
                snapshot.source_uri,
                snapshot.source_format,
                encode_datetime(snapshot.imported_at),
                metadata,
            ),
        )

    def _insert_node(self, snapshot_id: str, node: MutableNode) -> None:
        self._active().execute(
            "INSERT INTO nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                node.id,
                snapshot_id,
                node.parent_id,
                node.mounted_name,
                node.original_path,
                node.kind.value,
                node.size,
                encode_datetime(node.modified_at),
                node.content,
                ContentStatus.NOT_APPLICABLE.value,
                None,
                node.source_line,
                node.observation.value if node.observation else None,
                "{}",
            ),
        )

    def _update_node(self, node: MutableNode, metadata_json: str) -> None:
        self._active().execute(
            "UPDATE nodes SET original_path=?, size=?, modified_at=?, content=?, "
            "source_line=?, observation=?, metadata_json=? WHERE id=?",
            (
                node.original_path,
                node.size,
                encode_datetime(node.modified_at),
                node.content,
                node.source_line,
                node.observation.value if node.observation else None,
                metadata_json,
                node.id,
            ),
        )

    def _mutable(self, row: sqlite3.Row) -> MutableNode:
        mounted_name = row["mounted_name"]
        content = row["content"]
        if not isinstance(mounted_name, bytes):
            raise SQLitePersistenceError(
                self.destination, "temporary artifact mounted name is not a BLOB"
            )
        if content is not None and not isinstance(content, bytes):
            raise SQLitePersistenceError(
                self.destination, "temporary artifact content is not a BLOB"
            )
        return MutableNode(
            row["id"],
            row["parent_id"],
            mounted_name,
            row["original_path"],
            NodeKind(row["kind"]),
            row["size"],
            decode_datetime(row["modified_at"]),
            content,
            row["source_line"],
            None if row["observation"] is None else Observation(row["observation"]),
            decode_metadata(row["metadata_json"]),
        )

    def _active(self) -> sqlite3.Connection:
        if self._finished or self._connection is None:
            raise RuntimeError("builder is already finished")
        self._connection.row_factory = sqlite3.Row
        return self._connection

    def _close_connection(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _cleanup_temporary(self) -> None:
        cleanup(self._temporary)
        self._temporary = None
