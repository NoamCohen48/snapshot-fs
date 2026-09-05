"""Parser-to-import-service entry model."""

from dataclasses import dataclass, field
from datetime import datetime

from snapshotfs.model.enums import NodeKind, Observation
from snapshotfs.model.metadata import EMPTY_METADATA, Metadata, freeze_metadata


@dataclass(frozen=True, slots=True)
class ParsedEntry:
    path: tuple[str, ...]
    kind: NodeKind
    observation: Observation
    size: int | None
    modified_local: datetime | None
    source_line: int | None = None
    content: bytes | None = None
    source_metadata: Metadata = field(default_factory=lambda: EMPTY_METADATA)

    def __post_init__(self) -> None:
        if isinstance(self.path, str):
            raise TypeError("path must be a sequence of components, not a string")
        path = tuple(self.path)
        if any(not isinstance(component, str) for component in path):
            raise TypeError("path components must be strings")
        object.__setattr__(self, "path", path)
        if self.source_line is not None and (
            not isinstance(self.source_line, int)
            or isinstance(self.source_line, bool)
            or self.source_line <= 0
        ):
            raise ValueError("source line must be a positive integer or None")
        if self.kind is NodeKind.DIRECTORY:
            if self.size is not None or self.content is not None:
                raise ValueError("directories cannot have file content metadata")
        elif self.kind is NodeKind.FILE:
            if self.size is not None and self.size < 0:
                raise ValueError("file size cannot be negative")
            if self.content is not None and self.size != len(self.content):
                raise ValueError("content length must match the declared size")
        object.__setattr__(
            self, "source_metadata", freeze_metadata(self.source_metadata)
        )
