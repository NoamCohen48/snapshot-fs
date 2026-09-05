"""Optional pyfuse3 adapter for immutable snapshots."""

from snapshotfs.fuse.adapter.mount import mount_snapshot
from snapshotfs.fuse.adapter.operations import (
    ATTRIBUTE_TIMEOUT,
    CONTENT_STATUS_XATTR,
    SnapshotOperations,
)

__all__ = [
    "ATTRIBUTE_TIMEOUT",
    "CONTENT_STATUS_XATTR",
    "SnapshotOperations",
    "mount_snapshot",
]
