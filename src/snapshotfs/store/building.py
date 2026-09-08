"""Shared path normalization and entry merge semantics for store builders."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Never

from snapshotfs.diagnostics import ImportDiagnostic, Severity
from snapshotfs.model import ContentStatus, NodeKind, Observation, ParsedEntry

MAX_MOUNTED_NAME_BYTES = 255


class BuildError(ValueError):
    def __init__(self, diagnostic: ImportDiagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


@dataclass(slots=True)
class MutableNode:
    id: int
    parent_id: int | None
    mounted_name: bytes
    original_path: str | None
    kind: NodeKind
    size: int | None = None
    modified_at: datetime | None = None
    content: bytes | None = None
    source_line: int | None = None
    observation: Observation | None = None
    source_metadata: Mapping[str, Any] = MappingProxyType({})


def components(entry: ParsedEntry) -> list[bytes]:
    path_components = entry.path
    if not path_components:
        _invalid(entry, "path must contain at least one mounted component")
    result: list[bytes] = []
    for component in path_components:
        if not component or component in {".", ".."}:
            _invalid(entry, "path contains an empty or reserved component")
        if "\x00" in component or "/" in component:
            _invalid(entry, "path component contains NUL or forward slash")
        try:
            mounted_name = component.encode("utf-8")
        except UnicodeEncodeError:
            _invalid(entry, "path component is not valid Unicode")
        if len(mounted_name) > MAX_MOUNTED_NAME_BYTES:
            _invalid(entry, "path component exceeds the 255-byte mounted-name limit")
        result.append(mounted_name)
    return result


def merge(node: MutableNode, entry: ParsedEntry) -> None:
    if node.observation is None:
        apply_entry(node, entry)
        return
    if node.kind is NodeKind.FILE:
        if (
            node.size != entry.size
            or node.modified_at != entry.modified_local
            or node.content != entry.content
        ):
            conflict(node, entry, "incompatible duplicate file metadata")
        return
    if entry.observation is Observation.SECTION_HEADER:
        return
    if node.observation is Observation.SECTION_HEADER:
        apply_entry(node, entry)
        return
    if node.modified_at != entry.modified_local:
        conflict(node, entry, "incompatible duplicate directory metadata")


def apply_entry(node: MutableNode, entry: ParsedEntry) -> None:
    node.size = entry.size
    node.modified_at = entry.modified_local
    node.content = entry.content
    node.source_line = entry.source_line
    node.original_path = "/".join(entry.path)
    node.observation = entry.observation
    node.source_metadata = entry.source_metadata


def conflict(node: MutableNode, entry: ParsedEntry, reason: str) -> None:
    if node.source_line is not None:
        existing = f"line {node.source_line}"
    elif node.observation is not None and node.original_path is not None:
        existing = f"path {node.original_path!r}"
    else:
        existing = "synthesized node"
    incoming = (
        f"line {entry.source_line}"
        if entry.source_line is not None
        else f"path {'/'.join(entry.path)!r}"
    )
    raise BuildError(
        ImportDiagnostic(
            Severity.ERROR,
            "ENTRY_CONFLICT",
            f"{reason}: existing {existing}, incoming {incoming}",
            entry.source_line,
        )
    )


def entry_location(entry: ParsedEntry) -> str:
    if entry.source_line is not None:
        return f"line {entry.source_line}"
    return f"path {'/'.join(entry.path)!r}"


def content_values(node: MutableNode) -> tuple[bytes | None, ContentStatus]:
    content = (
        b""
        if node.kind is NodeKind.FILE and node.size == 0 and node.content is None
        else node.content
    )
    if node.kind is NodeKind.DIRECTORY:
        return content, ContentStatus.NOT_APPLICABLE
    if node.kind is NodeKind.FILE and content is not None:
        return content, ContentStatus.PRESENT
    return content, ContentStatus.MISSING


def _invalid(entry: ParsedEntry, message: str) -> Never:
    raise BuildError(
        ImportDiagnostic(Severity.ERROR, "INVALID_PATH", message, entry.source_line)
    )
