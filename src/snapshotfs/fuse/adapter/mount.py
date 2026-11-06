"""FUSE lifecycle orchestration."""

import os
import shutil
from pathlib import Path

import pyfuse3  # type: ignore[import-not-found]
import trio  # type: ignore[import-not-found]

from snapshotfs.fuse.adapter.operations import SnapshotOperations
from snapshotfs.store import SnapshotStore


def mount_snapshot(
    store: SnapshotStore,
    mountpoint: str,
    *,
    simulate_missing_content: bool = False,
) -> None:
    path = Path(mountpoint)
    if not path.is_dir():
        raise RuntimeError(f"mountpoint must be an existing directory: {path}")
    if os.path.ismount(path):
        raise RuntimeError(f"mountpoint is already mounted: {path}")
    if any(path.iterdir()):
        raise RuntimeError(f"mountpoint must be empty: {path}")
    if not Path("/dev/fuse").exists():
        raise RuntimeError(
            "/dev/fuse is unavailable; enable FUSE on the host "
            "(sudo modprobe fuse) and expose it to containers"
        )
    if not os.access("/dev/fuse", os.R_OK | os.W_OK):
        raise RuntimeError(
            "permission denied for /dev/fuse; check device "
            "permissions and container device access"
        )
    if shutil.which("fusermount3") is None:
        raise RuntimeError(
            "fusermount3 is unavailable; install the system fuse3 package"
        )
    operations = SnapshotOperations(
        store, simulate_missing_content=simulate_missing_content
    )
    options = set(pyfuse3.default_options)
    options.update({"fsname=snapshotfs", "ro"})
    try:
        pyfuse3.init(operations, mountpoint, options)
    except (OSError, RuntimeError) as exc:
        raise RuntimeError(
            f"cannot mount at {mountpoint}: {exc}. Check mountpoint ownership, "
            "/dev/fuse access, and container FUSE permissions."
        ) from exc
    try:
        trio.run(pyfuse3.main)
    finally:
        pyfuse3.close(unmount=True)
