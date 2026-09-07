import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from snapshotfs.cli import main
from snapshotfs.diagnostics import ImportDiagnostic, Severity
from snapshotfs.model import NodeKind, Observation, ParsedEntry, Snapshot
from snapshotfs.stores.sqlite import (
    SQLiteSchemaError,
    SQLiteSnapshotBuilder,
    open_sqlite_store,
)
from snapshotfs.stores.sqlite.schema import SCHEMA


def create_artifact(path: Path, *, diagnostic: bool = False) -> None:
    builder = SQLiteSnapshotBuilder(
        Snapshot("test", "memory:test", "test", datetime.now(UTC)), path
    )
    builder.add(
        ParsedEntry(
            ("dir",),
            NodeKind.DIRECTORY,
            Observation.DIRECTORY_ENTRY,
            None,
            datetime(2024, 1, 1),
            1,
        )
    )
    builder.add(
        ParsedEntry(
            ("dir", "file"),
            NodeKind.FILE,
            Observation.FILE_ENTRY,
            1,
            datetime(2024, 1, 1),
            2,
            b"x",
        )
    )
    diagnostics = (
        (ImportDiagnostic(Severity.WARNING, "WARNING", "warning", 3),)
        if diagnostic
        else ()
    )
    builder.finish(diagnostics).close()


def corrupt(path: Path, sql: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.executescript(sql)


def create_custom_artifact(
    path: Path, schema: str, *, duplicate_siblings: bool = False
) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(schema)
        connection.execute(
            "INSERT INTO snapshot VALUES ('test','source','format',?, '{}',0)",
            (datetime.now(UTC).isoformat(),),
        )
        connection.execute(
            "INSERT INTO nodes VALUES "
            "(1,'test',NULL,X'',NULL,'directory',NULL,NULL,NULL,"
            "'not_applicable',NULL,NULL,NULL,'{}')"
        )
        if duplicate_siblings:
            for inode in (2, 3):
                connection.execute(
                    "INSERT INTO nodes VALUES "
                    "(?,'test',1,X'61',NULL,'directory',NULL,NULL,NULL,"
                    "'not_applicable',NULL,NULL,NULL,'{}')",
                    (inode,),
                )


@pytest.mark.parametrize(
    ("sql", "message"),
    [
        ("UPDATE nodes SET parent_id=id WHERE mounted_name=X'646972'", "cycle"),
        (
            "UPDATE nodes SET kind='file', content_status='missing' "
            "WHERE mounted_name=X'646972'",
            "parent is not a directory",
        ),
        (
            "UPDATE nodes SET mounted_name=X'612F62' "
            "WHERE mounted_name=X'66696C65'",
            "invalid mounted name",
        ),
        (
            "UPDATE nodes SET mounted_name=X'FF' "
            "WHERE mounted_name=X'66696C65'",
            "not valid UTF-8",
        ),
        (
            "UPDATE nodes SET original_path='/' WHERE id=1",
            "virtual-root metadata",
        ),
        (
            "UPDATE nodes SET original_path='wrong' WHERE id=2",
            "derived relative path",
        ),
        (
            "UPDATE nodes SET content_status='remote', content_ref=NULL "
            "WHERE mounted_name=X'66696C65'",
            "invalid content metadata",
        ),
        (
            "UPDATE nodes SET kind='invalid' WHERE mounted_name=X'66696C65'",
            "invalid value",
        ),
        (
            "UPDATE nodes SET snapshot_id='other' WHERE mounted_name=X'66696C65'",
            "foreign keys",
        ),
        (
            "UPDATE nodes SET id=-2 WHERE id=2; "
            "UPDATE nodes SET parent_id=-2 WHERE parent_id=2",
            "invalid value",
        ),
        (
            "UPDATE nodes SET mounted_name=zeroblob(256) "
            "WHERE mounted_name=X'66696C65'",
            "255-byte limit",
        ),
    ],
)
def test_open_rejects_malicious_graph_and_node_records(
    tmp_path: Path, sql: str, message: str
) -> None:
    path = tmp_path / "malicious.db"
    create_artifact(path)
    corrupt(path, sql)
    with pytest.raises(SQLiteSchemaError, match=message):
        open_sqlite_store(path)


@pytest.mark.parametrize("column", ["mounted_name", "content"])
def test_type_confused_blob_columns_fail_without_integer_allocation(
    tmp_path: Path, column: str
) -> None:
    path = tmp_path / "type-confused.db"
    declaration = "mounted_name BLOB" if column == "mounted_name" else "content BLOB"
    altered = SCHEMA.replace(declaration, declaration.replace("BLOB", "ANY"))
    create_custom_artifact(path, altered)
    with sqlite3.connect(path) as connection:
        connection.execute(f"UPDATE nodes SET {column}=1000000000 WHERE id=1")
    with pytest.raises(SQLiteSchemaError, match="column contract"):
        open_sqlite_store(path)


@pytest.mark.parametrize(
    ("schema", "duplicate_siblings", "message"),
    [
        (
            SCHEMA.replace(" REFERENCES snapshot(id)", ""),
            False,
            "foreign-key contract",
        ),
        (
            SCHEMA.replace("CREATE INDEX nodes_snapshot_id ON nodes(snapshot_id);", ""),
            False,
            "nodes_snapshot_id",
        ),
        (
            SCHEMA.replace(
                "    metadata_json TEXT NOT NULL,\n"
                "    UNIQUE(parent_id, mounted_name)\n",
                "    metadata_json TEXT NOT NULL\n",
            ),
            True,
            "unique sibling constraints",
        ),
        (
            SCHEMA.replace("CHECK (id > 0)", "CHECK (id >= 0)"),
            False,
            "schema declaration",
        ),
        (
            SCHEMA.replace(
                "CHECK (id > 0)", "CHECK (id >= 0) /* CHECK (id > 0) */"
            ),
            False,
            "schema declaration",
        ),
    ],
)
def test_open_rejects_weakened_strict_schema_contract(
    tmp_path: Path, schema: str, duplicate_siblings: bool, message: str
) -> None:
    path = tmp_path / "weak.db"
    create_custom_artifact(path, schema, duplicate_siblings=duplicate_siblings)
    with pytest.raises(SQLiteSchemaError, match=message):
        open_sqlite_store(path)


@pytest.mark.parametrize("name", [b".", b".."])
def test_open_rejects_dot_mounted_names(tmp_path: Path, name: bytes) -> None:
    path = tmp_path / "dot.db"
    create_artifact(path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE nodes SET mounted_name=? WHERE mounted_name=X'66696C65'",
            (name,),
        )
    with pytest.raises(SQLiteSchemaError, match="invalid mounted name"):
        open_sqlite_store(path)


def test_temporary_validation_error_uses_destination_context(tmp_path: Path) -> None:
    destination = tmp_path / "destination.db"
    builder = SQLiteSnapshotBuilder(
        Snapshot("test", "source", "format", datetime.now(UTC)), destination
    )
    assert builder._connection is not None
    builder._connection.execute("DROP INDEX nodes_snapshot_id")
    with pytest.raises(SQLiteSchemaError) as caught:
        builder.finish()
    assert caught.value.path == destination
    assert ".tmp" not in str(caught.value)


def test_malformed_diagnostics_and_count_are_typed_and_cli_is_clean(
    tmp_path: Path, capsys
) -> None:
    path = tmp_path / "diagnostics.db"
    create_artifact(path, diagnostic=True)
    corrupt(path, "UPDATE diagnostics SET severity='bogus'")
    with pytest.raises(SQLiteSchemaError, match=r"diagnostics.*invalid value"):
        open_sqlite_store(path)
    assert main(["sqlite", "show", str(path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error: ")
    assert "Traceback" not in captured.err

    count_path = tmp_path / "count.db"
    create_artifact(count_path)
    corrupt(count_path, "UPDATE snapshot SET diagnostic_count=-1")
    with pytest.raises(SQLiteSchemaError, match=r"snapshot.*invalid value"):
        open_sqlite_store(count_path)


def test_diagnostic_access_wraps_post_open_corruption(tmp_path: Path) -> None:
    path = tmp_path / "live.db"
    create_artifact(path, diagnostic=True)
    with open_sqlite_store(path) as store:
        corrupt(path, "UPDATE diagnostics SET severity='bogus'")
        with pytest.raises(SQLiteSchemaError, match="diagnostic record"):
            _ = store.diagnostics
        corrupt(path, "UPDATE snapshot SET diagnostic_count=-1")
        with pytest.raises(SQLiteSchemaError, match="diagnostic count"):
            _ = store.diagnostic_count
