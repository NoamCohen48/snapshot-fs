"""Read-only pyfuse3 operations for immutable in-memory snapshots."""

import errno
import os
import stat
from collections.abc import Sequence
from datetime import UTC

import pyfuse3  # type: ignore[import-not-found]

from snapshotfs.fuse.adapter.read_only import ReadOnlyOperationsMixin
from snapshotfs.fuse.policy import ContentReadError, read_node
from snapshotfs.model import Node, NodeKind
from snapshotfs.stores.base import SnapshotStore

CONTENT_STATUS_XATTR = b"user.snapshotfs.content_status"
ATTRIBUTE_TIMEOUT = 300.0


class SnapshotOperations(  # type: ignore[misc]
    ReadOnlyOperationsMixin, pyfuse3.Operations
):
    """Read-only inode operations over an immutable snapshot store."""

    enable_writeback_cache = False

    def __init__(
        self, store: SnapshotStore, *, simulate_missing_content: bool = False
    ) -> None:
        super().__init__()
        self._store = store
        self._simulate_missing_content = simulate_missing_content
        root = next(iter(store.iter_nodes()))
        self._snapshot = store.get_snapshot(root.snapshot_id)
        self._file_handles: dict[int, int] = {}
        self._directory_handles: dict[int, int] = {}
        self._lookup_counts: dict[int, int] = {}
        self._next_handle = 1

    async def lookup(
        self,
        parent_inode: int,
        name: bytes,
        ctx: pyfuse3.RequestContext,
    ) -> pyfuse3.EntryAttributes:
        del ctx
        parent = self._node(parent_inode)
        if parent.kind is not NodeKind.DIRECTORY:
            raise pyfuse3.FUSEError(errno.ENOTDIR)
        if name == b".":
            node = parent
        elif name == b"..":
            node = parent if parent.parent_id is None else self._node(parent.parent_id)
        else:
            found = self._store.lookup(parent_inode, name)
            if found is None:
                raise pyfuse3.FUSEError(errno.ENOENT)
            node = found
        attributes = self._attributes(node)
        self._increment_lookup(node.id)
        return attributes

    async def forget(self, inode_list: Sequence[tuple[int, int]]) -> None:
        for inode, nlookup in inode_list:
            if nlookup <= 0:
                continue
            remaining = max(0, self._lookup_counts.get(inode, 0) - nlookup)
            if remaining:
                self._lookup_counts[inode] = remaining
            else:
                self._lookup_counts.pop(inode, None)

    async def getattr(
        self, inode: int, ctx: pyfuse3.RequestContext
    ) -> pyfuse3.EntryAttributes:
        del ctx
        return self._attributes(self._node(inode))

    async def opendir(self, inode: int, ctx: pyfuse3.RequestContext) -> int:
        del ctx
        node = self._node(inode)
        if node.kind is not NodeKind.DIRECTORY:
            raise pyfuse3.FUSEError(errno.ENOTDIR)
        handle = self._allocate_handle()
        self._directory_handles[handle] = inode
        return handle

    async def readdir(
        self, fh: int, start_id: int, token: pyfuse3.ReaddirToken
    ) -> None:
        try:
            inode = self._directory_handles[fh]
        except KeyError:
            raise pyfuse3.FUSEError(errno.EBADF) from None
        for next_id, node in enumerate(
            self._store.iter_children(inode, start_id), start=start_id + 1
        ):
            if not pyfuse3.readdir_reply(
                token, node.mounted_name, self._attributes(node), next_id
            ):
                break
            self._increment_lookup(node.id)

    async def releasedir(self, fh: int) -> None:
        if self._directory_handles.pop(fh, None) is None:
            raise pyfuse3.FUSEError(errno.EBADF)

    async def fsyncdir(self, fh: int, datasync: bool) -> None:
        del datasync
        self._directory_handle(fh)

    async def open(
        self, inode: int, flags: int, ctx: pyfuse3.RequestContext
    ) -> pyfuse3.FileInfo:
        del ctx
        node = self._node(inode)
        if node.kind is NodeKind.DIRECTORY:
            raise pyfuse3.FUSEError(errno.EISDIR)
        if node.kind is not NodeKind.FILE:
            raise pyfuse3.FUSEError(errno.EINVAL)
        if flags & os.O_ACCMODE != os.O_RDONLY or flags & (os.O_APPEND | os.O_TRUNC):
            raise pyfuse3.FUSEError(errno.EROFS)
        handle = self._allocate_handle()
        self._file_handles[handle] = inode
        return pyfuse3.FileInfo(fh=handle, keep_cache=True)

    async def read(self, fh: int, off: int, size: int) -> bytes:
        node = self._node(self._file_handle(fh))
        try:
            return read_node(
                node,
                off,
                size,
                simulate_missing=self._simulate_missing_content,
            )
        except ContentReadError as exc:
            assert exc.errno is not None
            raise pyfuse3.FUSEError(exc.errno) from None

    async def release(self, fh: int) -> None:
        if self._file_handles.pop(fh, None) is None:
            raise pyfuse3.FUSEError(errno.EBADF)

    async def flush(self, fh: int) -> None:
        self._file_handle(fh)

    async def fsync(self, fh: int, datasync: bool) -> None:
        del datasync
        self._file_handle(fh)

    async def getxattr(
        self, inode: int, name: bytes, ctx: pyfuse3.RequestContext
    ) -> bytes:
        del ctx
        node = self._node(inode)
        if name != CONTENT_STATUS_XATTR:
            raise pyfuse3.FUSEError(pyfuse3.ENOATTR)
        return node.content_status.value.encode("ascii")

    async def listxattr(
        self, inode: int, ctx: pyfuse3.RequestContext
    ) -> tuple[bytes, ...]:
        del ctx
        self._node(inode)
        return (CONTENT_STATUS_XATTR,)

    async def access(self, inode: int, mode: int, ctx: pyfuse3.RequestContext) -> bool:
        del ctx
        self._node(inode)
        if mode & os.W_OK:
            raise pyfuse3.FUSEError(errno.EROFS)
        return True

    async def readlink(self, inode: int, ctx: pyfuse3.RequestContext) -> bytes:
        del ctx
        self._node(inode)
        raise pyfuse3.FUSEError(errno.EINVAL)

    def _attributes(self, node: Node) -> pyfuse3.EntryAttributes:
        attributes = pyfuse3.EntryAttributes()
        attributes.st_ino = node.id
        attributes.generation = 0
        attributes.entry_timeout = ATTRIBUTE_TIMEOUT
        attributes.attr_timeout = ATTRIBUTE_TIMEOUT
        permissions = 0o555 if node.kind is NodeKind.DIRECTORY else 0o444
        file_type = stat.S_IFDIR if node.kind is NodeKind.DIRECTORY else stat.S_IFREG
        attributes.st_mode = file_type | permissions
        attributes.st_nlink = 2 if node.kind is NodeKind.DIRECTORY else 1
        attributes.st_uid = os.getuid()
        attributes.st_gid = os.getgid()
        attributes.st_rdev = 0
        attributes.st_size = node.size or 0
        attributes.st_blksize = 4096
        attributes.st_blocks = (attributes.st_size + 511) // 512
        timestamp = node.modified_at or self._snapshot.imported_at
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        timestamp_ns = int(timestamp.timestamp() * 1_000_000_000)
        attributes.st_atime_ns = timestamp_ns
        attributes.st_ctime_ns = timestamp_ns
        attributes.st_mtime_ns = timestamp_ns
        attributes.st_birthtime_ns = timestamp_ns
        return attributes

    def _node(self, inode: int) -> Node:
        try:
            return self._store.get_node(inode)
        except KeyError:
            raise pyfuse3.FUSEError(errno.ENOENT) from None

    def _allocate_handle(self) -> int:
        handle = self._next_handle
        self._next_handle += 1
        return handle

    def lookup_count(self, inode: int) -> int:
        """Return the current kernel lookup count for adapter contract tests."""
        return self._lookup_counts.get(inode, 0)

    def _increment_lookup(self, inode: int) -> None:
        self._lookup_counts[inode] = self._lookup_counts.get(inode, 0) + 1

    def _file_handle(self, handle: int) -> int:
        try:
            return self._file_handles[handle]
        except KeyError:
            raise pyfuse3.FUSEError(errno.EBADF) from None

    def _directory_handle(self, handle: int) -> int:
        try:
            return self._directory_handles[handle]
        except KeyError:
            raise pyfuse3.FUSEError(errno.EBADF) from None
