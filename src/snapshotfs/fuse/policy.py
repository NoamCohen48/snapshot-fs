"""Pure read policy for mounted snapshot nodes."""

import errno

from snapshotfs.model import ContentStatus, Node, NodeKind


class ContentReadError(OSError):
    def __init__(self, error_number: int) -> None:
        super().__init__(error_number, "snapshot content is unavailable")


def read_node(
    node: Node, offset: int, size: int, *, simulate_missing: bool = False
) -> bytes:
    """Return a bounded read without materializing an entire simulated file."""
    if node.kind is NodeKind.DIRECTORY:
        raise ContentReadError(errno.EISDIR)
    if node.kind is not NodeKind.FILE or offset < 0 or size < 0:
        raise ContentReadError(errno.EINVAL)
    if size == 0:
        return b""
    if node.size is not None and offset >= node.size:
        return b""
    if node.content is not None:
        return node.content[offset : offset + size]
    if (
        simulate_missing
        and node.content_status is ContentStatus.MISSING
        and node.size is not None
        and node.size >= 0
    ):
        return b"\0" * min(size, node.size - offset)
    raise ContentReadError(errno.ENODATA)
