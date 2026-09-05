"""SQLite artifact schema and connection configuration."""

import sqlite3

SCHEMA_VERSION = 4
APPLICATION_ID = 0x534E4653

SCHEMA = f"""
PRAGMA application_id = {APPLICATION_ID};
PRAGMA user_version = {SCHEMA_VERSION};
CREATE TABLE snapshot (
    id TEXT PRIMARY KEY,
    source_uri TEXT NOT NULL,
    source_format TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    diagnostic_count INTEGER NOT NULL CHECK (diagnostic_count >= 0)
) STRICT;
CREATE TABLE nodes (
    id INTEGER PRIMARY KEY CHECK (id > 0),
    snapshot_id TEXT NOT NULL REFERENCES snapshot(id),
    parent_id INTEGER REFERENCES nodes(id),
    mounted_name BLOB NOT NULL,
    original_path TEXT,
    kind TEXT NOT NULL,
    size INTEGER CHECK (size IS NULL OR size >= 0),
    modified_at TEXT,
    content BLOB,
    content_status TEXT NOT NULL,
    content_ref TEXT,
    source_line INTEGER CHECK (source_line IS NULL OR source_line > 0),
    observation TEXT,
    metadata_json TEXT NOT NULL,
    UNIQUE(parent_id, mounted_name)
) STRICT;
CREATE TABLE diagnostics (
    position INTEGER PRIMARY KEY CHECK (position >= 0),
    severity TEXT NOT NULL,
    code TEXT NOT NULL,
    message TEXT NOT NULL,
    line_number INTEGER CHECK (line_number IS NULL OR line_number > 0)
) STRICT;
CREATE INDEX nodes_snapshot_id ON nodes(snapshot_id);
CREATE INDEX nodes_parent_name ON nodes(parent_id, mounted_name);
"""


def configure(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")


def create_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA journal_mode = DELETE")
    connection.execute("PRAGMA synchronous = FULL")
    connection.executescript(SCHEMA)
