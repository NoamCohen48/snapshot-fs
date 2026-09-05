"""Explicit read-only implementations of mutating FUSE callbacks."""

import errno
from typing import NoReturn, Protocol

import pyfuse3  # type: ignore[import-not-found]


class _HasFileHandles(Protocol):
    def _file_handle(self, handle: int) -> int: ...

    def _read_only(self) -> NoReturn: ...


class ReadOnlyOperationsMixin:
    async def setattr(
        self,
        inode: int,
        attr: pyfuse3.EntryAttributes,
        fields: pyfuse3.SetattrFields,
        fh: int | None,
        ctx: pyfuse3.RequestContext,
    ) -> pyfuse3.EntryAttributes:
        del inode, attr, fields, fh, ctx
        self._read_only()

    async def mknod(
        self,
        parent_inode: int,
        name: bytes,
        mode: int,
        rdev: int,
        ctx: pyfuse3.RequestContext,
    ) -> pyfuse3.EntryAttributes:
        del parent_inode, name, mode, rdev, ctx
        self._read_only()

    async def mkdir(
        self, parent_inode: int, name: bytes, mode: int, ctx: pyfuse3.RequestContext
    ) -> pyfuse3.EntryAttributes:
        del parent_inode, name, mode, ctx
        self._read_only()

    async def unlink(
        self, parent_inode: int, name: bytes, ctx: pyfuse3.RequestContext
    ) -> None:
        del parent_inode, name, ctx
        self._read_only()

    async def rmdir(
        self, parent_inode: int, name: bytes, ctx: pyfuse3.RequestContext
    ) -> None:
        del parent_inode, name, ctx
        self._read_only()

    async def symlink(
        self,
        parent_inode: int,
        name: bytes,
        target: bytes,
        ctx: pyfuse3.RequestContext,
    ) -> pyfuse3.EntryAttributes:
        del parent_inode, name, target, ctx
        self._read_only()

    async def rename(
        self,
        parent_inode_old: int,
        name_old: bytes,
        parent_inode_new: int,
        name_new: bytes,
        flags: int,
        ctx: pyfuse3.RequestContext,
    ) -> None:
        del parent_inode_old, name_old, parent_inode_new, name_new, flags, ctx
        self._read_only()

    async def link(
        self,
        inode: int,
        new_parent_inode: int,
        new_name: bytes,
        ctx: pyfuse3.RequestContext,
    ) -> pyfuse3.EntryAttributes:
        del inode, new_parent_inode, new_name, ctx
        self._read_only()

    async def create(
        self,
        parent_inode: int,
        name: bytes,
        mode: int,
        flags: int,
        ctx: pyfuse3.RequestContext,
    ) -> tuple[pyfuse3.FileInfo, pyfuse3.EntryAttributes]:
        del parent_inode, name, mode, flags, ctx
        self._read_only()

    async def write(self: _HasFileHandles, fh: int, off: int, buf: bytes) -> int:
        del off, buf
        self._file_handle(fh)
        self._read_only()

    async def setxattr(
        self,
        inode: int,
        name: bytes,
        value: bytes,
        ctx: pyfuse3.RequestContext,
    ) -> None:
        del inode, name, value, ctx
        self._read_only()

    async def removexattr(
        self, inode: int, name: bytes, ctx: pyfuse3.RequestContext
    ) -> None:
        del inode, name, ctx
        self._read_only()

    @staticmethod
    def _read_only() -> NoReturn:
        raise pyfuse3.FUSEError(errno.EROFS)
