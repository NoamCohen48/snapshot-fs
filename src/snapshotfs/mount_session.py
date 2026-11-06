"""Process-managed CLI mount lifetimes with a readiness handshake."""

import os
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path

from snapshotfs.logging_setup import logger

WORKER_ENV = "SNAPSHOTFS_MOUNT_WORKER"
READY_ENV = "SNAPSHOTFS_MOUNT_READY_FD"


def cli_executable() -> list[str]:
    return (
        [sys.executable]
        if getattr(sys, "frozen", False)
        else [sys.executable, "-m", "snapshotfs.cli"]
    )


def external_environment() -> dict[str, str]:
    env = dict(os.environ)
    if getattr(sys, "frozen", False) and sys.platform == "linux":
        # External tools must use host libraries, not the frozen runtime's copies.
        original = env.pop("LD_LIBRARY_PATH_ORIG", None)
        if original:
            env["LD_LIBRARY_PATH"] = original
        else:
            env.pop("LD_LIBRARY_PATH", None)
    return env


def stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        process.wait()
        return
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
        with suppress(ProcessLookupError):
            os.killpg(process.pid, sig)
        try:
            process.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            continue


def is_snapshot_mount(path: Path) -> bool:
    # mountinfo paths escape spaces, tabs, newlines, and backslashes as octal.
    import re

    target = str(path.resolve())
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        fields = line.split()
        separator = fields.index("-")
        mountpoint = re.sub(
            r"\\(040|011|012|134)", lambda match: chr(int(match[1], 8)), fields[4]
        )
        if mountpoint == target:
            return fields[separator + 1] == "fuse.snapshotfs" or (
                fields[separator + 1] == "fuse"
                and fields[separator + 2] == "snapshotfs"
            )
    return False


def unmount(path: Path, timeout: float = 10) -> None:
    if sys.platform != "linux":
        raise RuntimeError("FUSE unmounting requires Linux")
    path = path.resolve()
    if not is_snapshot_mount(path):
        raise RuntimeError(f"not a SnapshotFS mount: {path}")
    helper = shutil.which("fusermount3")
    if helper is None:
        raise RuntimeError("install the system fuse3 package for fusermount3")
    logger.info("Requesting unmount at %s", path)
    result = subprocess.run(
        [helper, "-u", "--", str(path)],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=external_environment(),
    )
    if result.returncode:
        raise RuntimeError(f"cannot unmount {path}: {result.stderr.strip()}")
    deadline = time.monotonic() + timeout
    while os.path.ismount(path):
        if time.monotonic() >= deadline:
            raise RuntimeError(f"unmount timed out: {path}")
        time.sleep(0.05)


def start_background(
    arguments: Sequence[str], mountpoint: Path, timeout: float
) -> subprocess.Popen[bytes]:
    if sys.platform != "linux":
        raise RuntimeError("background FUSE mounting requires Linux")
    if (
        not mountpoint.is_dir()
        or os.path.ismount(mountpoint)
        or any(mountpoint.iterdir())
    ):
        raise RuntimeError(
            f"mountpoint must be an existing, empty, unmounted directory: {mountpoint}"
        )
    read_fd, write_fd = os.pipe()
    process = None
    try:
        env = {
            **external_environment(),
            WORKER_ENV: "1",
            READY_ENV: str(write_fd),
            # A detached onefile worker must own its extracted runtime.
            "PYINSTALLER_RESET_ENVIRONMENT": "1",
        }
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(
                [*cli_executable(), *arguments],
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=errors,
                start_new_session=True,
                pass_fds=(write_fd,),
            )
            os.close(write_fd)
            write_fd = -1
            ready, _, _ = select.select([read_fd], [], [], timeout)
            if (
                ready
                and os.read(read_fd, 1) == b"1"
                and os.path.ismount(mountpoint)
                and process.poll() is None
            ):
                logger.info(
                    "Background mount ready: %s pid=%d", mountpoint, process.pid
                )
                return process
            stop_process(process)
            errors.seek(0)
            detail = errors.read(8192).decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"mount did not become ready within {timeout:g}s: "
                f"{detail or 'see diagnostic log'}"
            )
    except BaseException:
        if process is not None:
            stop_process(process)
        raise
    finally:
        os.close(read_fd)
        if write_fd != -1:
            os.close(write_fd)


def run_mounted(
    snapshot: str,
    command: Sequence[str],
    options: Sequence[str],
    *,
    simulate: bool,
    timeout: float,
) -> int:
    if not command:
        raise ValueError("provide a command after --")
    mountpoint = Path(tempfile.mkdtemp(prefix="snapshotfs-"))
    worker = None
    consumer = None
    try:
        arguments = [
            *options,
            "sqlite",
            "mount",
            str(Path(snapshot).resolve()),
            str(mountpoint),
        ]
        if simulate:
            arguments.append("--simulate-missing-content")
        worker = start_background(arguments, mountpoint, timeout)
        argv = [value.replace("{mountpoint}", str(mountpoint)) for value in command]
        logger.info("Running command in mount session: %r", argv)
        consumer = subprocess.Popen(
            argv,
            env={**external_environment(), "SNAPSHOTFS_MOUNTPOINT": str(mountpoint)},
            start_new_session=True,
        )
        status = consumer.wait()
        return status if status >= 0 else 128 - status
    finally:
        if consumer is not None and consumer.poll() is None:
            stop_process(consumer)
        try:
            if worker is not None and os.path.ismount(mountpoint):
                unmount(mountpoint)
        finally:
            if worker is not None:
                stop_process(worker)
            if not os.path.ismount(mountpoint):
                mountpoint.rmdir()
