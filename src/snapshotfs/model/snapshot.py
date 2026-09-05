"""Imported snapshot metadata."""

from dataclasses import dataclass, field
from datetime import datetime

from snapshotfs.model.metadata import EMPTY_METADATA, Metadata, freeze_metadata


@dataclass(frozen=True, slots=True)
class Snapshot:
    id: str
    source_uri: str
    source_format: str
    imported_at: datetime
    source_metadata: Metadata = field(default_factory=lambda: EMPTY_METADATA)

    def __post_init__(self) -> None:
        for description, value in (
            ("snapshot ID", self.id),
            ("source URI", self.source_uri),
            ("source format", self.source_format),
        ):
            try:
                value.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise ValueError(f"{description} is not valid Unicode") from exc
        object.__setattr__(
            self, "source_metadata", freeze_metadata(self.source_metadata)
        )
