"""Exact schema contract validation for version-4 artifacts."""

import re
import sqlite3
from pathlib import Path
from typing import Never

from snapshotfs.stores.sqlite.errors import SQLiteSchemaError
from snapshotfs.stores.sqlite.schema import SCHEMA

type Column = tuple[str, str, int, object, int, int]

TABLES: dict[str, tuple[Column, ...]] = {
    "snapshot": (
        ("id", "TEXT", 1, None, 1, 0),
        ("source_uri", "TEXT", 1, None, 0, 0),
        ("source_format", "TEXT", 1, None, 0, 0),
        ("imported_at", "TEXT", 1, None, 0, 0),
        ("metadata_json", "TEXT", 1, None, 0, 0),
        ("diagnostic_count", "INTEGER", 1, None, 0, 0),
    ),
    "nodes": (
        ("id", "INTEGER", 0, None, 1, 0),
        ("snapshot_id", "TEXT", 1, None, 0, 0),
        ("parent_id", "INTEGER", 0, None, 0, 0),
        ("mounted_name", "BLOB", 1, None, 0, 0),
        ("original_path", "TEXT", 0, None, 0, 0),
        ("kind", "TEXT", 1, None, 0, 0),
        ("size", "INTEGER", 0, None, 0, 0),
        ("modified_at", "TEXT", 0, None, 0, 0),
        ("content", "BLOB", 0, None, 0, 0),
        ("content_status", "TEXT", 1, None, 0, 0),
        ("content_ref", "TEXT", 0, None, 0, 0),
        ("source_line", "INTEGER", 0, None, 0, 0),
        ("observation", "TEXT", 0, None, 0, 0),
        ("metadata_json", "TEXT", 1, None, 0, 0),
    ),
    "diagnostics": (
        ("position", "INTEGER", 0, None, 1, 0),
        ("severity", "TEXT", 1, None, 0, 0),
        ("code", "TEXT", 1, None, 0, 0),
        ("message", "TEXT", 1, None, 0, 0),
        ("line_number", "INTEGER", 0, None, 0, 0),
    ),
}

FOREIGN_KEYS = {
    ("nodes", "parent_id", "id", "NO ACTION", "NO ACTION", "NONE"),
    ("snapshot", "snapshot_id", "id", "NO ACTION", "NO ACTION", "NONE"),
}
UNIQUE_SIBLING_KEYS = {
    (("parent_id", "BINARY", 0), ("mounted_name", "BINARY", 0)),
}
REQUIRED_INDEXES = {
    "nodes_snapshot_id": (("snapshot_id", "BINARY", 0),),
    "nodes_parent_name": (
        ("parent_id", "BINARY", 0),
        ("mounted_name", "BINARY", 0),
    ),
}
def validate_schema_contract(connection: sqlite3.Connection, path: Path) -> None:
    table_rows = connection.execute(
        "SELECT name, type, wr, strict FROM pragma_table_list "
        "WHERE schema='main' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    actual_tables = {row[0] for row in table_rows}
    if actual_tables != set(TABLES):
        _fail(path, "artifact does not contain the exact required tables")
    if any(row[1] != "table" or row[2] != 0 or row[3] != 1 for row in table_rows):
        _fail(path, "artifact tables must be ordinary STRICT rowid tables")
    for table, expected in TABLES.items():
        rows = connection.execute(
            'SELECT name, type, "notnull", dflt_value, pk, hidden '
            "FROM pragma_table_xinfo(?) ORDER BY cid",
            (table,),
        ).fetchall()
        if tuple(tuple(row) for row in rows) != expected:
            _fail(path, f"table {table} has an invalid column contract")
    _validate_foreign_keys(connection, path)
    _validate_indexes(connection, path)
    for table in TABLES:
        _validate_table_declaration(connection, path, table)


def _validate_foreign_keys(connection: sqlite3.Connection, path: Path) -> None:
    rows = connection.execute(
        'SELECT "table", "from", "to", on_update, on_delete, match '
        "FROM pragma_foreign_key_list('nodes')"
    ).fetchall()
    if len(rows) != len(FOREIGN_KEYS) or {tuple(row) for row in rows} != FOREIGN_KEYS:
        _fail(path, "nodes has an invalid foreign-key contract")
    for table in ("snapshot", "diagnostics"):
        if connection.execute(
            "SELECT 1 FROM pragma_foreign_key_list(?) LIMIT 1", (table,)
        ).fetchone():
            _fail(path, f"table {table} has an unexpected foreign key")


def _validate_table_declaration(
    connection: sqlite3.Connection, path: Path, table: str
) -> None:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if row is None or not isinstance(row[0], str):
        _fail(path, f"table {table} has no schema declaration")
    expected = re.search(
        rf"CREATE TABLE {re.escape(table)}\s*\(.*?\)\s*STRICT;",
        SCHEMA,
        flags=re.DOTALL,
    )
    assert expected is not None
    if _normalize_sql(row[0]) != _normalize_sql(expected.group(0)):
        _fail(path, f"table {table} has an invalid schema declaration")


def _normalize_sql(statement: str) -> str:
    return " ".join(statement.rstrip("; ").lower().split())


def _validate_indexes(connection: sqlite3.Connection, path: Path) -> None:
    rows = connection.execute(
        "SELECT name, \"unique\", origin, partial FROM pragma_index_list('nodes')"
    ).fetchall()
    by_name = {row[0]: tuple(row[1:]) for row in rows}
    unique_rows = [
        row
        for row in rows
        if row[1] == 1 and row[2] == "u" and row[3] == 0
    ]
    unique_keys = {_index_details(connection, row[0]) for row in unique_rows}
    if len(unique_rows) != 1 or unique_keys != UNIQUE_SIBLING_KEYS:
        _fail(path, "nodes has invalid unique sibling constraints")
    for name, expected in REQUIRED_INDEXES.items():
        if by_name.get(name) != (0, "c", 0):
            _fail(path, f"required index {name} is missing or invalid")
        if _index_details(connection, name) != expected:
            _fail(path, f"required index {name} has invalid columns")


def _index_details(
    connection: sqlite3.Connection, name: str
) -> tuple[tuple[str, str, int], ...]:
    rows = connection.execute(
        "SELECT name, coll, desc FROM pragma_index_xinfo(?) "
        "WHERE key=1 ORDER BY seqno",
        (name,),
    ).fetchall()
    return tuple((row[0], row[1], row[2]) for row in rows)


def _fail(path: Path, message: str) -> Never:
    raise SQLiteSchemaError(path, message)
