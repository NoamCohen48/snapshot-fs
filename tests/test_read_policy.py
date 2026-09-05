import errno

import pytest

from snapshotfs.fuse.policy import ContentReadError, read_node
from snapshotfs.model import ContentStatus, Node, NodeKind


def node(
    *,
    kind: NodeKind = NodeKind.FILE,
    size: int | None = 8,
    content: bytes | None = None,
    status: ContentStatus = ContentStatus.MISSING,
    content_ref: str | None = None,
) -> Node:
    return Node(
        2,
        "snapshot",
        1,
        b"file",
        r"C:\file",
        kind,
        size,
        None,
        content,
        status,
        content_ref,
        1,
    )


def test_inline_content_reads_requested_slice() -> None:
    inline = node(size=8, content=b"contents", status=ContentStatus.PRESENT)
    assert read_node(inline, 2, 3) == b"nte"
    assert read_node(inline, 8, 3) == b""
    assert read_node(inline, 0, 0) == b""


def test_missing_content_is_unavailable_by_default_but_has_known_eof() -> None:
    missing = node()
    with pytest.raises(ContentReadError) as caught:
        read_node(missing, 0, 4)
    assert caught.value.errno == errno.ENODATA
    assert read_node(missing, 8, 4) == b""


def test_simulation_is_bounded_to_request_and_remaining_size() -> None:
    huge = node(size=10**12)
    assert read_node(huge, 10**12 - 3, 10, simulate_missing=True) == b"\0" * 3
    assert len(read_node(huge, 0, 7, simulate_missing=True)) == 7


@pytest.mark.parametrize(
    "unavailable",
    [
        node(size=None),
        node(status=ContentStatus.REMOTE, content_ref="remote:value"),
        node(status=ContentStatus.FAILED),
        node(status=ContentStatus.REDACTED),
        node(status=ContentStatus.PRESENT, content_ref="sha256:value"),
    ],
)
def test_simulation_does_not_mask_other_unavailable_states(
    unavailable: Node,
) -> None:
    with pytest.raises(ContentReadError) as caught:
        read_node(unavailable, 0, 4, simulate_missing=True)
    assert caught.value.errno == errno.ENODATA


def test_zero_length_file_always_returns_eof() -> None:
    empty = node(size=0, content=b"", status=ContentStatus.PRESENT)
    assert read_node(empty, 0, 100) == b""


def test_invalid_read_arguments_and_directory_are_rejected() -> None:
    with pytest.raises(ContentReadError) as negative:
        read_node(node(), -1, 1)
    assert negative.value.errno == errno.EINVAL

    directory = node(
        kind=NodeKind.DIRECTORY,
        size=None,
        status=ContentStatus.NOT_APPLICABLE,
    )
    with pytest.raises(ContentReadError) as is_directory:
        read_node(directory, 0, 1)
    assert is_directory.value.errno == errno.EISDIR
