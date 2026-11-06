"""Opt-in kernel mount smoke test.

Set SNAPSHOTFS_MOUNT_TEST=1 only on a host where mounting FUSE filesystems is
permitted. Cleanup is attempted even when the assertion path fails.
"""

import errno
import os
import shlex
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
    not _ENABLED,
    reason="set SNAPSHOTFS_MOUNT_TEST=1 on a usable libfuse host",
)
@pytest.mark.parametrize("backend", ["memory", "sqlite"])
@pytest.mark.parametrize("simulate", [False, True])
def test_kernel_mount_smoke(
    listing_file: Path, tmp_path: Path, backend: str, simulate: bool
) -> None:
    if not os.environ.get("SNAPSHOTFS_TEST_CLI"):
        __import__("pyfuse3")
    assert Path("/dev/fuse").exists(), "FUSE device must be exposed for mount tests"
    assert _FUSERMOUNT is not None, "fusermount3 must be installed for mount tests"
    mountpoint = tmp_path / "mount"
    mountpoint.mkdir()
    executable = shlex.split(os.environ.get("SNAPSHOTFS_TEST_CLI", "")) or [
        sys.executable,
        "-m",
        "snapshotfs.cli",
    ]
    selectors = ["--source", "file", "--parser", "windows-dir"]
    if backend == "memory":
        command = [
            *executable,
            "memory",
            "mount",
            str(mountpoint),
            str(listing_file),
            *selectors,
        ]
    else:
        artifact = tmp_path / "snapshot.db"
        subprocess.run(
            [
                *executable,
                "sqlite",
                "create",
                str(artifact),
                str(listing_file),
                *selectors,
            ],
            check=True,
        )
        command = [
            *executable,
            "sqlite",
            "mount",
            str(artifact),
            str(mountpoint),
        ]
    if simulate:
        command.append("--simulate-missing-content")
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
        listed_file = mountpoint / "C" / "Users" / "Alice" / "notes file.txt"
        if simulate:
            assert listed_file.read_bytes() == bytes(1234)
        else:
            with pytest.raises(OSError) as caught:
                listed_file.read_bytes()
            assert caught.value.errno == errno.ENODATA
        with pytest.raises(OSError) as caught:
            (mountpoint / "new-file").write_text("forbidden")
        assert caught.value.errno in {errno.EROFS, errno.EACCES}
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

        if process.stderr is not None:
            stderr = process.stderr.read()
            if stderr:
                print(stderr, file=sys.stderr)

    assert not os.path.ismount(mountpoint)
