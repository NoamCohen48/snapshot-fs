"""FUSE lifecycle orchestration."""

import pyfuse3  # type: ignore[import-not-found]
import trio  # type: ignore[import-not-found]

from snapshotfs.fuse.adapter.operations import SnapshotOperations
from snapshotfs.stores.base import SnapshotStore


def mount_snapshot(
    store: SnapshotStore,
    mountpoint: str,
    *,
    simulate_missing_content: bool = False,
) -> None:
    operations = SnapshotOperations(
        store, simulate_missing_content=simulate_missing_content
    )
    options = set(pyfuse3.default_options)
    options.update({"fsname=snapshotfs", "ro"})
    pyfuse3.init(operations, mountpoint, options)
    try:
        trio.run(pyfuse3.main)
    finally:
        pyfuse3.close(unmount=True)
