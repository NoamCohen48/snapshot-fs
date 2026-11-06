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
    else:
        command.append("--foreground")
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


def executable_cli() -> list[str]:
    return shlex.split(os.environ.get("SNAPSHOTFS_TEST_CLI", "")) or [
        sys.executable,
        "-m",
        "snapshotfs.cli",
    ]


def make_artifact(listing_file: Path, tmp_path: Path) -> Path:
    artifact = tmp_path / "session.db"
    subprocess.run(
        [
            *executable_cli(),
            "sqlite",
            "create",
            str(artifact),
            "--source",
            "file",
            str(listing_file),
            "--parser",
            "windows-dir",
            "--source-timezone",
            "Asia/Jerusalem",
        ],
        check=True,
        timeout=20,
    )
    return artifact


@pytest.mark.skipif(not _ENABLED, reason="requires opted-in FUSE host")
@pytest.mark.parametrize("backend", ["memory", "sqlite", "create"])
def test_one_shot_background_and_unmount(
    listing_file: Path, tmp_path: Path, backend: str
) -> None:
    from datetime import datetime, timedelta, timezone

    mountpoint = tmp_path / "background mount"
    mountpoint.mkdir()
    if backend == "sqlite":
        args = [
            "sqlite",
            "mount",
            str(make_artifact(listing_file, tmp_path)),
            str(mountpoint),
        ]
    else:
        args = (
            ["memory", "mount", str(mountpoint)]
            if backend == "memory"
            else [
                "sqlite",
                "create",
                str(tmp_path / "created.db"),
                "--mount",
                str(mountpoint),
            ]
        )
        args += [
            "--source",
            "file",
            str(listing_file),
            "--parser",
            "windows-dir",
            "--source-timezone",
            "Asia/Jerusalem",
        ]
    try:
        result = subprocess.run(
            [*executable_cli(), *args, "--background", "--startup-timeout", "20"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert os.path.ismount(mountpoint)
        file = mountpoint / "C/Users/Alice/notes file.txt"
        expected = datetime(
            2024, 1, 2, 15, 5, tzinfo=timezone(timedelta(hours=2))
        ).timestamp()
        assert file.stat().st_mtime == expected
        subprocess.run(
            [*executable_cli(), "unmount", str(mountpoint)], check=True, timeout=20
        )
        assert not os.path.ismount(mountpoint)
    finally:
        if os.path.ismount(mountpoint):
            subprocess.run(["fusermount3", "-u", str(mountpoint)], check=False)


@pytest.mark.skipif(not _ENABLED, reason="requires opted-in FUSE host")
@pytest.mark.parametrize(
    "outcome", ["success", "failure", "missing-program", "interrupt"]
)
def test_command_scoped_mount_cleans_up(
    listing_file: Path, tmp_path: Path, outcome: str
) -> None:
    artifact = make_artifact(listing_file, tmp_path)
    recorded_path = tmp_path / "mount-path"
    code = (
        "import pathlib, sys, os, signal; "
        "p=pathlib.Path(sys.argv[1]); pathlib.Path(sys.argv[2]).write_text(str(p)); "
        "assert (p/'C/Users/Alice/notes file.txt').stat().st_size == 1234; "
        "assert os.environ['SNAPSHOTFS_MOUNTPOINT'] == str(p); "
        + (
            "os.kill(os.getpid(), signal.SIGINT)"
            if outcome == "interrupt"
            else f"sys.exit({7 if outcome == 'failure' else 0})"
        )
    )
    command = [sys.executable, "-c", code, "{mountpoint}", str(recorded_path)]
    if outcome == "missing-program":
        command = [str(tmp_path / "no-such-program")]
    result = subprocess.run(
        [*executable_cli(), "run", str(artifact), "--", *command],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert (
        result.returncode
        == {"success": 0, "failure": 7, "missing-program": 1, "interrupt": 130}[outcome]
    ), result.stderr
    if recorded_path.exists():
        path = Path(recorded_path.read_text())
        assert not os.path.ismount(path)
        assert not path.exists()


@pytest.mark.skipif(not _ENABLED, reason="requires opted-in FUSE host")
def test_background_import_failure_never_reports_ready(tmp_path: Path) -> None:
    mountpoint = tmp_path / "failed mount"
    mountpoint.mkdir()
    invalid = tmp_path / "invalid.txt"
    invalid.write_text("not a listing", encoding="utf-8")
    result = subprocess.run(
        [
            *executable_cli(),
            "memory",
            "mount",
            str(mountpoint),
            "--source",
            "file",
            str(invalid),
            "--parser",
            "windows-dir",
            "--background",
            "--startup-timeout",
            "10",
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 1
    assert "UNKNOWN_LINE" in result.stderr
    assert not os.path.ismount(mountpoint)


@pytest.mark.skipif(not _ENABLED, reason="requires opted-in FUSE host")
def test_interrupting_run_unmounts_and_stops_command(
    listing_file: Path, tmp_path: Path
) -> None:
    artifact = make_artifact(listing_file, tmp_path)
    recorded = tmp_path / "active-mount"
    code = (
        "import pathlib,sys,time; "
        "pathlib.Path(sys.argv[1]).write_text(sys.argv[2]); time.sleep(60)"
    )
    process = subprocess.Popen(
        [
            *executable_cli(),
            "run",
            str(artifact),
            "--",
            sys.executable,
            "-c",
            code,
            str(recorded),
            "{mountpoint}",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 20
        while not recorded.exists():
            if process.poll() is not None:
                pytest.fail(process.communicate()[1])
            assert time.monotonic() < deadline, "consumer did not start"
            time.sleep(0.05)
        mountpoint = Path(recorded.read_text())
        assert os.path.ismount(mountpoint)
        process.send_signal(signal.SIGINT)
        _, error = process.communicate(timeout=20)
        assert process.returncode == 130, error
        assert not os.path.ismount(mountpoint)
        assert not mountpoint.exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        if recorded.exists():
            path = Path(recorded.read_text())
            if os.path.ismount(path):
                subprocess.run(["fusermount3", "-u", str(path)], check=False)
