"""Enumerations shared by snapshot domain objects."""

from enum import StrEnum


class NodeKind(StrEnum):
    DIRECTORY = "directory"
    FILE = "file"
    SYMLINK = "symlink"
    SPECIAL = "special"
    UNKNOWN = "unknown"


class ContentStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    MISSING = "missing"
    PRESENT = "present"
    REMOTE = "remote"
    FAILED = "failed"
    REDACTED = "redacted"


class Observation(StrEnum):
    SECTION_HEADER = "section_header"
    DIRECTORY_ENTRY = "directory_entry"
    FILE_ENTRY = "file_entry"
