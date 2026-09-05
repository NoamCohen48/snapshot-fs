"""Normalized immutable filesystem node."""

from dataclasses import dataclass, field
from datetime import datetime

from snapshotfs.model.enums import ContentStatus, NodeKind
from snapshotfs.model.metadata import EMPTY_METADATA, Metadata, freeze_metadata


@dataclass(frozen=True, slots=True)
class Node:
    id: int
    snapshot_id: str
    parent_id: int | None
    mounted_name: bytes
    original_path: str | None
    kind: NodeKind
    size: int | None
    modified_at: datetime | None
    content: bytes | None
    content_status: ContentStatus
    content_ref: str | None
    source_line: int | None
    source_metadata: Metadata = field(default_factory=lambda: EMPTY_METADATA)

    def __post_init__(self) -> None:
        if self.kind is NodeKind.DIRECTORY:
            if (
                self.size is not None
                or self.content is not None
                or self.content_ref is not None
                or self.content_status is not ContentStatus.NOT_APPLICABLE
            ):
                raise ValueError("directories cannot have file content metadata")
        elif self.kind is NodeKind.FILE:
            self._validate_file()
        object.__setattr__(
            self, "source_metadata", freeze_metadata(self.source_metadata)
        )

    def _validate_file(self) -> None:
        if self.size is not None and self.size < 0:
            raise ValueError("file size cannot be negative")
        if self.content is not None and self.size != len(self.content):
            raise ValueError("content length must match the declared size")
        if self.content_status is ContentStatus.NOT_APPLICABLE:
            raise ValueError("file content status cannot be not_applicable")
        if self.size == 0 and (
            self.content != b""
            or self.content_status is not ContentStatus.PRESENT
            or self.content_ref is not None
        ):
            raise ValueError("zero-length files must contain present empty content")
        if self.content is not None:
            if self.content_status is not ContentStatus.PRESENT:
                raise ValueError("inline content must be present")
            if self.content_ref is not None:
                raise ValueError("inline content cannot also have a content reference")
        elif self.content_status is ContentStatus.PRESENT:
            if not self.content_ref:
                raise ValueError("external present content requires a reference")
        elif self.content_status is ContentStatus.REMOTE:
            if not self.content_ref:
                raise ValueError("remote content requires a reference")
        elif self.content_ref is not None:
            raise ValueError("only present or remote content may have a reference")
