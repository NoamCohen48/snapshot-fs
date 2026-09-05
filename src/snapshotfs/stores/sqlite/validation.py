"""Bounded validation for untrusted SQLite snapshot artifacts."""

import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Never

from snapshotfs.diagnostics import Severity
from snapshotfs.model import ContentStatus, NodeKind, Observation
from snapshotfs.stores.building import MAX_MOUNTED_NAME_BYTES
from snapshotfs.stores.sqlite.codec import decode_datetime, decode_metadata
from snapshotfs.stores.sqlite.errors import SQLiteSchemaError


def validate_records(connection: sqlite3.Connection, path: Path) -> None:
    _require_storage_classes(connection, path)
    _require_ranges_and_domain_values(connection, path)
    _require_graph(connection, path)
    _validate_names_and_serialized_values(connection, path)


def _require_storage_classes(connection: sqlite3.Connection, path: Path) -> None:
    checks = {
        "snapshot": """
            typeof(id) != 'text' OR typeof(source_uri) != 'text' OR
            typeof(source_format) != 'text' OR typeof(imported_at) != 'text' OR
            typeof(metadata_json) != 'text' OR typeof(diagnostic_count) != 'integer'
        """,
        "nodes": """
            typeof(id) != 'integer' OR typeof(snapshot_id) != 'text' OR
            typeof(parent_id) NOT IN ('null', 'integer') OR
            typeof(mounted_name) != 'blob' OR
            typeof(original_path) NOT IN ('null', 'text') OR typeof(kind) != 'text' OR
            typeof(size) NOT IN ('null', 'integer') OR
            typeof(modified_at) NOT IN ('null', 'text') OR
            typeof(content) NOT IN ('null', 'blob') OR
            typeof(content_status) != 'text' OR
            typeof(content_ref) NOT IN ('null', 'text') OR
            typeof(source_line) NOT IN ('null', 'integer') OR
            typeof(observation) NOT IN ('null', 'text') OR
            typeof(metadata_json) != 'text'
        """,
        "diagnostics": """
            typeof(position) != 'integer' OR typeof(severity) != 'text' OR
            typeof(code) != 'text' OR typeof(message) != 'text' OR
            typeof(line_number) NOT IN ('null', 'integer')
        """,
    }
    for table, condition in checks.items():
        if connection.execute(
            f"SELECT 1 FROM {table} WHERE {condition} LIMIT 1"
        ).fetchone():
            _fail(path, f"{table} contains an invalid SQLite storage class")


def _require_ranges_and_domain_values(
    connection: sqlite3.Connection, path: Path
) -> None:
    kinds = _sql_values(item.value for item in NodeKind)
    statuses = _sql_values(item.value for item in ContentStatus)
    observations = _sql_values(item.value for item in Observation)
    severities = _sql_values(item.value for item in Severity)
    checks = (
        ("snapshot", "diagnostic_count < 0"),
        (
            "nodes",
            f"id <= 0 OR (parent_id IS NOT NULL AND parent_id <= 0) OR "
            f"size < 0 OR source_line <= 0 OR kind NOT IN ({kinds}) OR "
            f"content_status NOT IN ({statuses}) OR "
            f"(observation IS NOT NULL AND observation NOT IN ({observations}))",
        ),
        (
            "diagnostics",
            f"position < 0 OR line_number <= 0 OR severity NOT IN ({severities})",
        ),
    )
    for table, condition in checks:
        if connection.execute(
            f"SELECT 1 FROM {table} WHERE {condition} LIMIT 1"
        ).fetchone():
            _fail(path, f"{table} contains an invalid value")
    diagnostic_positions = connection.execute(
        "SELECT COUNT(*), MIN(position), MAX(position) FROM diagnostics"
    ).fetchone()
    assert diagnostic_positions is not None
    count, minimum, maximum = diagnostic_positions
    if count and (minimum != 0 or maximum != count - 1):
        _fail(path, "diagnostic positions are not contiguous")
    _require_content_invariants(connection, path)


def _require_content_invariants(connection: sqlite3.Connection, path: Path) -> None:
    invalid = connection.execute(
        """
        SELECT 1 FROM nodes WHERE
          (kind = 'directory' AND (size IS NOT NULL OR content IS NOT NULL OR
             content_ref IS NOT NULL OR content_status != 'not_applicable')) OR
          (kind = 'file' AND (
             content_status = 'not_applicable' OR
             (size = 0 AND (content IS NULL OR length(content) != 0 OR
                content_status != 'present' OR content_ref IS NOT NULL)) OR
             (content IS NOT NULL AND (size IS NULL OR length(content) != size OR
                content_status != 'present' OR content_ref IS NOT NULL)) OR
             (content IS NULL AND content_status IN ('present', 'remote') AND
                (content_ref IS NULL OR content_ref = '')) OR
             (content IS NULL AND content_status NOT IN ('present', 'remote') AND
                content_ref IS NOT NULL)
          ))
        LIMIT 1
        """
    ).fetchone()
    if invalid:
        _fail(path, "nodes contain invalid content metadata")


def _require_graph(connection: sqlite3.Connection, path: Path) -> None:
    invalid_parent = connection.execute(
        """
        SELECT 1 FROM nodes child JOIN nodes parent ON parent.id = child.parent_id
        WHERE parent.kind != 'directory' LIMIT 1
        """
    ).fetchone()
    if invalid_parent:
        _fail(path, "a node parent is not a directory")
    total = int(connection.execute("SELECT COUNT(*) FROM nodes").fetchone()[0])
    reachable = int(
        connection.execute(
            """
            WITH RECURSIVE reachable(id) AS (
              SELECT 1
              UNION ALL
              SELECT nodes.id FROM nodes JOIN reachable
                ON nodes.parent_id = reachable.id
            )
            SELECT COUNT(*) FROM reachable
            """
        ).fetchone()[0]
    )
    if reachable != total:
        _fail(path, "filesystem graph contains a cycle or disconnected node")


def _validate_names_and_serialized_values(
    connection: sqlite3.Connection, path: Path
) -> None:
    root = connection.execute(
        "SELECT original_path, modified_at, source_line, observation, metadata_json "
        "FROM nodes WHERE id=1"
    ).fetchone()
    assert root is not None
    if tuple(root) != (None, None, None, None, "{}"):
        _fail(path, "inode 1 has invalid virtual-root metadata")
    oversized = connection.execute(
        "SELECT 1 FROM nodes WHERE length(mounted_name) > ? LIMIT 1",
        (MAX_MOUNTED_NAME_BYTES,),
    ).fetchone()
    if oversized:
        _fail(path, "mounted name exceeds the FUSE-compatible 255-byte limit")
    cursor = connection.execute(
        "SELECT id, mounted_name, modified_at, metadata_json FROM nodes"
    )
    for inode, raw_name, modified_at, metadata_json in cursor:
        if not isinstance(raw_name, bytes):
            _fail(path, f"inode {inode} mounted name is not a BLOB")
        try:
            name = raw_name.decode("utf-8")
        except UnicodeDecodeError as exc:
            _fail(path, f"inode {inode} mounted name is not valid UTF-8: {exc}")
        if inode == 1:
            if raw_name != b"":
                _fail(path, "inode 1 has an invalid root name")
        elif not raw_name or name in {".", ".."} or "\x00" in name or "/" in name:
            _fail(path, f"inode {inode} has an invalid mounted name")
        _decode_values(path, f"inode {inode}", modified_at, metadata_json)
    invalid_path = connection.execute(
        """
        WITH RECURSIVE paths(id, relative_path) AS (
          SELECT id, '' FROM nodes WHERE id = 1
          UNION ALL
          SELECT child.id,
            CASE WHEN paths.relative_path = ''
              THEN CAST(child.mounted_name AS TEXT)
              ELSE paths.relative_path || '/' || CAST(child.mounted_name AS TEXT)
            END
          FROM nodes child JOIN paths ON child.parent_id = paths.id
        )
        SELECT 1 FROM paths JOIN nodes USING (id)
        WHERE id != 1 AND (
          nodes.original_path IS NULL OR nodes.original_path != paths.relative_path
        )
        LIMIT 1
        """
    ).fetchone()
    if invalid_path:
        _fail(path, "node has an invalid derived relative path")
    row = connection.execute(
        "SELECT imported_at, metadata_json FROM snapshot"
    ).fetchone()
    assert row is not None
    _decode_values(path, "snapshot", row[0], row[1], timestamp_required=True)


def _decode_values(
    path: Path,
    context: str,
    timestamp: str | None,
    metadata_json: str,
    *,
    timestamp_required: bool = False,
) -> None:
    try:
        decoded = decode_datetime(timestamp)
        if timestamp_required and decoded is None:
            raise ValueError("timestamp is required")
        decode_metadata(metadata_json)
    except (TypeError, ValueError) as exc:
        _fail(path, f"{context} has invalid serialized data: {exc}")


def _sql_values(values: Iterable[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _fail(path: Path, message: str) -> Never:
    raise SQLiteSchemaError(path, message)
