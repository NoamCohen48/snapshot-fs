"""Public read-only FUSE mounting API and dependency-free read policies."""

from importlib import import_module
from os import PathLike, fspath
from typing import Protocol, cast

from snapshotfs.fuse.policy import ContentReadError, read_node
from snapshotfs.store import SnapshotStore


class _MountSnapshot(Protocol):
    def __call__(
        self,
        store: SnapshotStore,
        mountpoint: str,
        *,
        simulate_missing_content: bool = False,
    ) -> None: ...


class FuseUnavailableError(RuntimeError):
    """Raised when the optional FUSE dependencies are not installed."""


def mount_store(
    store: SnapshotStore,
    mountpoint: str | PathLike[str],
    *,
    simulate_missing_content: bool = False,
) -> None:
    """Mount an already imported snapshot store."""
    try:
        adapter = import_module("snapshotfs.fuse.adapter")
    except ModuleNotFoundError as exc:
        if exc.name not in {"pyfuse3", "trio"}:
            raise
        raise FuseUnavailableError(
            "FUSE support is unavailable; install the 'fuse' extra"
        ) from exc
    mount_snapshot = cast(_MountSnapshot, adapter.mount_snapshot)
    mount_snapshot(
        store,
        fspath(mountpoint),
        simulate_missing_content=simulate_missing_content,
    )

__all__ = ["ContentReadError", "FuseUnavailableError", "mount_store", "read_node"]
