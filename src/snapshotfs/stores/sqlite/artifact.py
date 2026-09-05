"""Temporary artifact creation, cleanup, and atomic publication."""

import os
import tempfile
from contextlib import suppress
from pathlib import Path

from snapshotfs.stores.sqlite.errors import (
    SQLiteDestinationExistsError,
    SQLiteDurabilityError,
    SQLitePersistenceError,
    SQLitePublicationError,
)

DIRECTORY_FSYNC_SUPPORTED = os.name != "nt"


def create_temporary(destination: Path) -> Path:
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
    except OSError as exc:
        raise SQLitePersistenceError(
            destination, f"cannot create temporary artifact: {exc}"
        ) from exc
    os.close(descriptor)
    return Path(temporary)


def publish(temporary: Path, destination: Path, *, overwrite: bool) -> None:
    try:
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
    except OSError as exc:
        raise SQLitePersistenceError(
            destination, f"cannot sync temporary artifact: {exc}"
        ) from exc
    try:
        if overwrite:
            os.replace(temporary, destination)
        else:
            os.link(temporary, destination)
            try:
                temporary.unlink()
            except OSError as exc:
                raise SQLitePublicationError(
                    destination,
                    "artifact was published, but its temporary link could not "
                    f"be removed: {exc}",
                ) from exc
    except FileExistsError as exc:
        raise SQLiteDestinationExistsError(
            destination, "destination already exists (use overwrite=True)"
        ) from exc
    except OSError as exc:
        raise SQLitePersistenceError(
            destination, f"cannot publish artifact: {exc}"
        ) from exc

    if not DIRECTORY_FSYNC_SUPPORTED:
        return
    try:
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        raise SQLiteDurabilityError(
            destination,
            "artifact was published, but the destination directory could not "
            f"be synced: {exc}",
        ) from exc


def cleanup(temporary: Path | None) -> None:
    if temporary is None:
        return
    for path in (
        temporary,
        Path(f"{temporary}-wal"),
        Path(f"{temporary}-shm"),
        Path(f"{temporary}-journal"),
    ):
        with suppress(OSError):
            path.unlink()
