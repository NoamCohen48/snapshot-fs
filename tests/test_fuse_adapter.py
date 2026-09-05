import errno
import importlib
import os
import stat
from datetime import UTC, datetime

import pytest

from snapshotfs.model import NodeKind, Observation, ParsedEntry, Snapshot
from snapshotfs.stores.memory import InMemorySnapshotBuilder, InMemorySnapshotStore

pyfuse3 = pytest.importorskip("pyfuse3")
trio = pytest.importorskip("trio")
adapter = importlib.import_module("snapshotfs.fuse.adapter")
CONTENT_STATUS_XATTR = adapter.CONTENT_STATUS_XATTR
SnapshotOperations = adapter.SnapshotOperations


def store() -> InMemorySnapshotStore:
    builder = InMemorySnapshotBuilder(
        Snapshot("test", "file:///test", "test", datetime.now(UTC))
    )
    modified = datetime(2024, 1, 2, 3, 4)
    builder.add(
        ParsedEntry(
            ("C", "directory"),
            NodeKind.DIRECTORY,
            Observation.DIRECTORY_ENTRY,
            None,
            modified,
            1,
        )
    )
    builder.add(
        ParsedEntry(
            ("C", "inline"),
            NodeKind.FILE,
            Observation.FILE_ENTRY,
            6,
            modified,
            2,
            b"abcdef",
        )
    )
    builder.add(
        ParsedEntry(
            ("C", "missing"),
            NodeKind.FILE,
            Observation.FILE_ENTRY,
            5,
            modified,
            3,
        )
    )
    builder.add(
        ParsedEntry(
            ("C", "zero"),
            NodeKind.FILE,
            Observation.FILE_ENTRY,
            0,
            modified,
            4,
        )
    )
    return builder.finish()


def child(snapshot: InMemorySnapshotStore, name: bytes):
    drive = snapshot.lookup(1, b"C")
    assert drive is not None
    result = snapshot.lookup(drive.id, name)
    assert result is not None
    return result


def assert_fuse_error(caught: pytest.ExceptionInfo[Exception], expected: int) -> None:
    assert isinstance(caught.value, pyfuse3.FUSEError)
    assert getattr(caught.value, "errno", None) == expected


def test_lookup_getattr_and_type_errors() -> None:
    snapshot = store()
    operations = SnapshotOperations(snapshot)

    async def exercise() -> None:
        drive_attr = await operations.lookup(1, b"C", None)
        drive = snapshot.lookup(1, b"C")
        assert drive is not None
        assert drive_attr.st_ino == drive.id
        assert stat.S_ISDIR(drive_attr.st_mode)
        assert drive_attr.st_mode & 0o777 == 0o555
        repeated = await operations.getattr(drive_attr.st_ino, None)
        assert repeated.st_ino == drive_attr.st_ino
        with pytest.raises(pyfuse3.FUSEError) as missing:
            await operations.lookup(1, b"absent", None)
        assert_fuse_error(missing, errno.ENOENT)
        with pytest.raises(pyfuse3.FUSEError) as not_directory:
            await operations.lookup(child(snapshot, b"inline").id, b"name", None)
        assert_fuse_error(not_directory, errno.ENOTDIR)

    trio.run(exercise)


def test_successful_lookup_increments_and_failed_lookup_does_not() -> None:
    snapshot = store()
    operations = SnapshotOperations(snapshot)
    drive = snapshot.lookup(1, b"C")
    assert drive is not None

    async def exercise() -> None:
        assert operations.lookup_count(drive.id) == 0
        await operations.lookup(1, b"C", None)
        await operations.lookup(1, b"C", None)
        assert operations.lookup_count(drive.id) == 2
        with pytest.raises(pyfuse3.FUSEError):
            await operations.lookup(1, b"absent", None)
        assert operations.lookup_count(drive.id) == 2

    trio.run(exercise)


def test_directory_handles_and_deterministic_offsets(monkeypatch) -> None:
    snapshot = store()
    operations = SnapshotOperations(snapshot)
    drive = snapshot.lookup(1, b"C")
    assert drive is not None
    replies: list[tuple[bytes, int]] = []

    def reply(token, name, attributes, next_id):
        del token, attributes
        replies.append((name, next_id))
        return True

    monkeypatch.setattr(pyfuse3, "readdir_reply", reply)

    async def exercise() -> None:
        handle = await operations.opendir(drive.id, None)
        await operations.readdir(handle, 0, object())
        assert replies == [
            (b"directory", 1),
            (b"inline", 2),
            (b"missing", 3),
            (b"zero", 4),
        ]
        replies.clear()
        await operations.readdir(handle, 2, object())
        assert replies == [(b"missing", 3), (b"zero", 4)]
        await operations.releasedir(handle)
        with pytest.raises(pyfuse3.FUSEError) as bad_handle:
            await operations.readdir(handle, 0, object())
        assert_fuse_error(bad_handle, errno.EBADF)
        with pytest.raises(pyfuse3.FUSEError) as not_directory:
            await operations.opendir(child(snapshot, b"inline").id, None)
        assert_fuse_error(not_directory, errno.ENOTDIR)

    trio.run(exercise)


def test_readdir_counts_only_accepted_replies(monkeypatch) -> None:
    snapshot = store()
    operations = SnapshotOperations(snapshot)
    drive = snapshot.lookup(1, b"C")
    assert drive is not None
    directory = child(snapshot, b"directory")
    inline = child(snapshot, b"inline")
    missing = child(snapshot, b"missing")

    def reply(token, name, attributes, next_id):
        del token, attributes, next_id
        return name != b"inline"

    monkeypatch.setattr(pyfuse3, "readdir_reply", reply)

    async def exercise() -> None:
        handle = await operations.opendir(drive.id, None)
        await operations.readdir(handle, 0, object())
        assert operations.lookup_count(directory.id) == 1
        assert operations.lookup_count(inline.id) == 0
        assert operations.lookup_count(missing.id) == 0

    trio.run(exercise)


def test_forget_decrements_batches_without_underflow_or_node_removal() -> None:
    snapshot = store()
    operations = SnapshotOperations(snapshot)
    drive = snapshot.lookup(1, b"C")
    assert drive is not None
    inline = child(snapshot, b"inline")

    async def exercise() -> None:
        await operations.lookup(1, b"C", None)
        await operations.lookup(1, b"C", None)
        await operations.lookup(drive.id, b"inline", None)
        assert operations.lookup_count(drive.id) == 2
        assert operations.lookup_count(inline.id) == 1

        await operations.forget([(drive.id, 1), (inline.id, 1)])
        assert operations.lookup_count(drive.id) == 1
        assert operations.lookup_count(inline.id) == 0

        await operations.forget([(drive.id, 50), (999_999, 2), (inline.id, -1)])
        assert operations.lookup_count(drive.id) == 0
        assert operations.lookup_count(inline.id) == 0
        assert (await operations.getattr(drive.id, None)).st_ino == drive.id
        assert (await operations.getattr(inline.id, None)).st_ino == inline.id

    trio.run(exercise)


def test_open_read_release_and_simulation() -> None:
    snapshot = store()
    operations = SnapshotOperations(snapshot)
    simulated = SnapshotOperations(snapshot, simulate_missing_content=True)

    async def exercise() -> None:
        inline = child(snapshot, b"inline")
        info = await operations.open(inline.id, os.O_RDONLY, None)
        assert await operations.read(info.fh, 1, 3) == b"bcd"
        await operations.release(info.fh)
        with pytest.raises(pyfuse3.FUSEError) as bad_handle:
            await operations.read(info.fh, 0, 1)
        assert_fuse_error(bad_handle, errno.EBADF)

        missing = child(snapshot, b"missing")
        missing_info = await operations.open(missing.id, os.O_RDONLY, None)
        with pytest.raises(pyfuse3.FUSEError) as no_data:
            await operations.read(missing_info.fh, 0, 2)
        assert_fuse_error(no_data, errno.ENODATA)
        assert await operations.read(missing_info.fh, 5, 2) == b""

        simulated_info = await simulated.open(missing.id, os.O_RDONLY, None)
        assert await simulated.read(simulated_info.fh, 3, 8) == b"\0\0"
        zero = child(snapshot, b"zero")
        zero_info = await simulated.open(zero.id, os.O_RDONLY, None)
        assert await simulated.read(zero_info.fh, 0, 8) == b""

        with pytest.raises(pyfuse3.FUSEError) as is_directory:
            await operations.open(child(snapshot, b"directory").id, os.O_RDONLY, None)
        assert_fuse_error(is_directory, errno.EISDIR)
        with pytest.raises(pyfuse3.FUSEError) as read_write:
            await operations.open(inline.id, os.O_RDWR, None)
        assert_fuse_error(read_write, errno.EROFS)

    trio.run(exercise)


def test_xattrs_and_mutations_are_read_only() -> None:
    snapshot = store()
    operations = SnapshotOperations(snapshot)
    missing = child(snapshot, b"missing")

    async def exercise() -> None:
        assert (
            await operations.getxattr(missing.id, CONTENT_STATUS_XATTR, None)
            == b"missing"
        )
        assert await operations.listxattr(missing.id, None) == (CONTENT_STATUS_XATTR,)
        with pytest.raises(pyfuse3.FUSEError) as no_attribute:
            await operations.getxattr(missing.id, b"user.other", None)
        assert_fuse_error(no_attribute, pyfuse3.ENOATTR)
        with pytest.raises(pyfuse3.FUSEError) as mkdir:
            await operations.mkdir(1, b"new", 0o755, None)
        assert_fuse_error(mkdir, errno.EROFS)

        info = await operations.open(missing.id, os.O_RDONLY, None)
        with pytest.raises(pyfuse3.FUSEError) as write:
            await operations.write(info.fh, 0, b"x")
        assert_fuse_error(write, errno.EROFS)

    trio.run(exercise)
