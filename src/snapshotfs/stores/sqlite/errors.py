"""Typed SQLite artifact failures."""

from pathlib import Path


class SQLiteStoreError(RuntimeError):
    """Base class for SQLite persistence and artifact errors."""

    def __init__(self, path: str | Path, message: str) -> None:
        self.path = Path(path)
        self.detail = message
        super().__init__(f"{self.path}: {message}")


class SQLitePersistenceError(SQLiteStoreError):
    """An artifact could not be created or published."""


class SQLiteSchemaError(SQLiteStoreError):
    """An artifact has an unsupported or invalid schema."""


class SQLiteStoreClosedError(SQLiteStoreError):
    """A read was attempted after the store was closed."""


class SQLiteDestinationExistsError(SQLitePersistenceError):
    """Publication was refused because the destination already exists."""


class SQLiteDurabilityError(SQLitePersistenceError):
    """Publication occurred but its directory entry could not be made durable."""


class SQLitePublicationError(SQLitePersistenceError):
    """Publication completed with a failure cleaning its temporary link."""


__all__ = [
    "SQLiteDestinationExistsError",
    "SQLiteDurabilityError",
    "SQLitePersistenceError",
    "SQLitePublicationError",
    "SQLiteSchemaError",
    "SQLiteStoreClosedError",
    "SQLiteStoreError",
]
