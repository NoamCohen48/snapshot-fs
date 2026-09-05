"""Opt-in kernel mount smoke test.

Set SNAPSHOTFS_MOUNT_TEST=1 only on a host where mounting FUSE filesystems is
permitted. Cleanup is attempted even when the assertion path fails.
"""

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

_ENABLED = os.environ.get("SNAPSHOTFS_MOUNT_TEST") == "1"
_FUSERMOUNT = shutil.which("fusermount3")


@pytest.mark.skipif(
    not _ENABLED or not Path("/dev/fuse").exists() or _FUSERMOUNT is None,
    reason="set SNAPSHOTFS_MOUNT_TEST=1 on a usable libfuse host",
)
@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_kernel_mount_smoke(listing_file: Path, tmp_path: Path, backend: str) -> None:
    pytest.importorskip("pyfuse3")
    assert _FUSERMOUNT is not None
    mountpoint = tmp_path / "mount"
    mountpoint.mkdir()
    selectors = ["--source", "file", "--parser", "windows-dir"]
    if backend == "memory":
        command = [
            sys.executable,
            "-m",
            "snapshotfs.cli",
            "mount",
            str(listing_file),
            *selectors,
            str(mountpoint),
        ]
    else:
        artifact = tmp_path / "snapshot.db"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "snapshotfs.cli",
                "import",
                str(artifact),
                str(listing_file),
                *selectors,
            ],
            check=True,
        )
        command = [
            sys.executable,
            "-m",
            "snapshotfs.cli",
            "mount-store",
            str(artifact),
            str(mountpoint),
        ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 10
        while not os.path.ismount(mountpoint):
            if process.poll() is not None:
                _, stderr = process.communicate()
                pytest.fail(f"mount exited before becoming ready: {stderr}")
            if time.monotonic() >= deadline:
                pytest.fail("mount did not become ready within 10 seconds")
            time.sleep(0.05)
        assert sorted(os.listdir(mountpoint)) == ["C"]
        assert (
            mountpoint / "C" / "Users" / "Alice" / "notes file.txt"
        ).stat().st_size == 1234
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)
        if os.path.ismount(mountpoint):
            subprocess.run(
                [_FUSERMOUNT, "-u", str(mountpoint)],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
