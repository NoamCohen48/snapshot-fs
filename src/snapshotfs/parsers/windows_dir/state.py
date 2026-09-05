"""Mutable validation state for Windows directory sections and footers."""

from dataclasses import dataclass
from pathlib import PureWindowsPath

from snapshotfs.diagnostics import DiagnosticCollector


@dataclass(slots=True)
class SectionState:
    path: PureWindowsPath | None = None
    line: int | None = None
    files: int = 0
    size: int = 0
    file_summary: bool = False
    dir_summary: bool = False
    reported_files: int = 0
    reported_size: int = 0
    had_entries: bool = False
    file_not_found: bool = False
    mountable: bool = False

    def start(self, path: PureWindowsPath, line: int, *, mountable: bool) -> None:
        self.path = path
        self.line = line
        self.files = 0
        self.size = 0
        self.file_summary = False
        self.dir_summary = False
        self.reported_files = 0
        self.reported_size = 0
        self.had_entries = False
        self.file_not_found = False
        self.mountable = mountable

    def close(self, diagnostics: DiagnosticCollector) -> None:
        if self.path is None:
            return
        if not self.file_summary:
            diagnostics.error(
                "MISSING_SECTION_FILE_SUMMARY",
                "directory section is missing its File(s) summary",
                self.line,
            )
        if not self.dir_summary:
            diagnostics.error(
                "MISSING_SECTION_DIR_SUMMARY",
                "directory section is missing its Dir(s) summary",
                self.line,
            )
        if self.file_summary and (self.reported_files, self.reported_size) != (
            self.files,
            self.size,
        ):
            diagnostics.error(
                "SECTION_FILE_TOTAL_MISMATCH",
                f"section reports {self.reported_files} files/"
                f"{self.reported_size} bytes; parsed {self.files} files/"
                f"{self.size} bytes",
                self.line,
            )
        self.path = None


@dataclass(slots=True)
class AggregateState:
    active: bool = False
    file_summary: bool = False
    dir_summary: bool = False
