import pytest

from snapshotfs.model import (
    ContentStatus,
    Node,
    NodeKind,
    Observation,
    ParsedEntry,
)


def node(
    *,
    kind: NodeKind = NodeKind.FILE,
    size: int | None = 1,
    content: bytes | None = None,
    status: ContentStatus = ContentStatus.MISSING,
    content_ref: str | None = None,
) -> Node:
    return Node(
        2,
        "snapshot",
        1,
        b"name",
        r"C:\name",
        kind,
        size,
        None,
        content,
        status,
        content_ref,
        1,
    )


def test_valid_inline_external_remote_and_missing_content() -> None:
    assert node(size=1, content=b"x", status=ContentStatus.PRESENT).content == b"x"
    external = node(status=ContentStatus.PRESENT, content_ref="sha256:value")
    remote = node(status=ContentStatus.REMOTE, content_ref="https://example.test")
    assert external.content is None
    assert remote.content is None
    assert node().content_status is ContentStatus.MISSING
    assert node(size=0, content=b"", status=ContentStatus.PRESENT).content == b""


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": ContentStatus.PRESENT},
        {"status": ContentStatus.REMOTE},
        {"content": b"x", "status": ContentStatus.REMOTE},
        {"content": b"x", "status": ContentStatus.PRESENT, "content_ref": "ref"},
        {"status": ContentStatus.MISSING, "content_ref": "ref"},
        {"size": 0, "status": ContentStatus.MISSING},
        {"size": 0, "status": ContentStatus.PRESENT},
        {"size": -1},
        {"status": ContentStatus.NOT_APPLICABLE},
    ],
)
def test_invalid_file_content_states_are_rejected(kwargs: object) -> None:
    with pytest.raises(ValueError):
        node(**kwargs)  # type: ignore[arg-type]


def test_directory_content_invariants_are_enforced() -> None:
    assert (
        node(
            kind=NodeKind.DIRECTORY,
            size=None,
            status=ContentStatus.NOT_APPLICABLE,
        ).content_status
        is ContentStatus.NOT_APPLICABLE
    )
    with pytest.raises(ValueError):
        node(kind=NodeKind.DIRECTORY, size=None, status=ContentStatus.MISSING)


def test_metadata_is_deeply_immutable_and_detached_from_input() -> None:
    original = {"nested": {"items": [1, {"value": "original"}]}}
    value = Node(
        2,
        "snapshot",
        1,
        b"name",
        r"C:\name",
        NodeKind.FILE,
        1,
        None,
        None,
        ContentStatus.MISSING,
        None,
        1,
        original,
    )
    original["nested"]["items"].append(2)  # type: ignore[union-attr]
    nested = value.source_metadata["nested"]
    with pytest.raises(TypeError):
        nested["changed"] = True  # type: ignore[index]
    items = nested["items"]  # type: ignore[index]
    with pytest.raises(AttributeError):
        items.append(3)
    assert items == (1, {"value": "original"})


def test_parsed_entry_path_components_are_immutable() -> None:
    components = ["bucket", r"folder\name:part"]
    entry = ParsedEntry(
        components,  # type: ignore[arg-type]
        NodeKind.DIRECTORY,
        Observation.DIRECTORY_ENTRY,
        None,
        None,
    )
    components.append("changed")
    assert entry.path == ("bucket", r"folder\name:part")
    with pytest.raises(TypeError, match="sequence of components"):
        ParsedEntry(
            "not/components",  # type: ignore[arg-type]
            NodeKind.DIRECTORY,
            Observation.DIRECTORY_ENTRY,
            None,
            None,
        )


@pytest.mark.parametrize("source_line", [0, -1, True, 1.5, "1"])
def test_parsed_entry_rejects_invalid_optional_source_lines(
    source_line: object,
) -> None:
    with pytest.raises(ValueError, match="positive integer or None"):
        ParsedEntry(
            ("file",),
            NodeKind.FILE,
            Observation.FILE_ENTRY,
            0,
            None,
            source_line,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "value",
    [
        {"bad": {1}},
        {"bad": (1,)},
        {"bad": float("nan")},
        {1: "non-string key"},
        {"bad\ud800key": "value"},
        {"bad": "value\ud800"},
    ],
)
def test_metadata_is_limited_to_backend_independent_json_values(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        Node(
            2,
            "snapshot",
            1,
            b"name",
            "/name",
            NodeKind.FILE,
            1,
            None,
            None,
            ContentStatus.MISSING,
            None,
            None,
            value,  # type: ignore[arg-type]
        )
