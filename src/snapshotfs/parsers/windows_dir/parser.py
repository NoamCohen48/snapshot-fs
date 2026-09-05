"""Streaming state machine for Windows ``dir /s`` listings."""

from collections.abc import Iterator
from pathlib import PureWindowsPath
from typing import BinaryIO

from snapshotfs.decoding import DecodeError, iter_decoded_lines
from snapshotfs.diagnostics import DiagnosticCollector
from snapshotfs.model import NodeKind, Observation, ParsedEntry
from snapshotfs.parsers.base import ParseResult
from snapshotfs.parsers.windows_dir.grammar import (
    DateFormat,
    dir_summary,
    file_summary,
    header_path,
    is_volume,
    parse_entry,
    parse_integer,
    resembles_entry,
    valid_section_path,
)
from snapshotfs.parsers.windows_dir.paths import to_mounted_path
from snapshotfs.parsers.windows_dir.state import AggregateState, SectionState


class WindowsDirParser:
    format_name = "windows-dir"

    def __init__(
        self, encoding: str = "utf-8", date_format: DateFormat | str = DateFormat.MDY
    ) -> None:
        self.encoding = encoding
        self.date_format = DateFormat(date_format)

    def parse(self, stream: BinaryIO) -> ParseResult:
        diagnostics = DiagnosticCollector()
        return ParseResult(self._parse(stream, diagnostics), diagnostics)

    def _parse(
        self, stream: BinaryIO, diagnostics: DiagnosticCollector
    ) -> Iterator[ParsedEntry]:
        section = SectionState()
        aggregate = AggregateState()
        total_files = 0
        total_size = 0
        saw_section = False
        try:
            for decoded in iter_decoded_lines(stream, self.encoding):
                line = decoded.text
                number = decoded.number
                if not line.strip() or is_volume(line):
                    continue
                raw_path = header_path(line)
                if raw_path is not None:
                    if aggregate.active:
                        diagnostics.error(
                            "SECTION_AFTER_AGGREGATE",
                            "directory section appears after aggregate footer",
                            number,
                        )
                        continue
                    section.close(diagnostics)
                    valid_path = valid_section_path(raw_path)
                    unsafe_path = "\x00" in raw_path or "/" in raw_path
                    if unsafe_path:
                        diagnostics.error(
                            "INVALID_SECTION_PATH",
                            "section path contains NUL or forward slash",
                            number,
                        )
                    elif not valid_path:
                        diagnostics.error(
                            "INVALID_SECTION_PATH",
                            "section path contains an empty component or "
                            "unsupported alternate data stream",
                            number,
                        )
                    path = PureWindowsPath(raw_path)
                    mountable = valid_path and not unsafe_path
                    section.start(path, number, mountable=mountable)
                    saw_section = True
                    if mountable:
                        yield ParsedEntry(
                            to_mounted_path(path),
                            NodeKind.DIRECTORY,
                            Observation.SECTION_HEADER,
                            None,
                            None,
                            number,
                        )
                    continue
                if line.strip() == "Total Files Listed:":
                    section.close(diagnostics)
                    if aggregate.active:
                        diagnostics.error(
                            "DUPLICATE_AGGREGATE_FOOTER",
                            "duplicate Total Files Listed footer",
                            number,
                        )
                    aggregate.active = True
                    continue
                summary = file_summary(line)
                if summary is not None:
                    count, size = (parse_integer(value) for value in summary)
                    if count is None or size is None:
                        diagnostics.error(
                            "INVALID_SUMMARY_NUMBER", "invalid summary number", number
                        )
                    elif aggregate.active:
                        if aggregate.file_summary:
                            diagnostics.error(
                                "DUPLICATE_AGGREGATE_FILE_SUMMARY",
                                "duplicate aggregate File(s) summary",
                                number,
                            )
                        aggregate.file_summary = True
                        if aggregate.dir_summary:
                            diagnostics.error(
                                "AGGREGATE_FILE_SUMMARY_AFTER_DIR_SUMMARY",
                                "aggregate File(s) summary appears after "
                                "Dir(s) summary",
                                number,
                            )
                        if (count, size) != (total_files, total_size):
                            diagnostics.error(
                                "AGGREGATE_FILE_TOTAL_MISMATCH",
                                f"aggregate reports {count} files/{size} bytes; "
                                f"parsed {total_files} files/{total_size} bytes",
                                number,
                            )
                    elif section.path is None:
                        diagnostics.error(
                            "SUMMARY_OUTSIDE_SECTION",
                            "File(s) summary appears outside a section",
                            number,
                        )
                    else:
                        if section.file_summary:
                            diagnostics.error(
                                "DUPLICATE_SECTION_FILE_SUMMARY",
                                "duplicate section File(s) summary",
                                number,
                            )
                        section.file_summary = True
                        section.reported_files = count
                        section.reported_size = size
                    continue
                summary = dir_summary(line)
                if summary is not None:
                    if any(parse_integer(value) is None for value in summary):
                        diagnostics.error(
                            "INVALID_SUMMARY_NUMBER", "invalid summary number", number
                        )
                    elif aggregate.active:
                        if aggregate.dir_summary:
                            diagnostics.error(
                                "DUPLICATE_AGGREGATE_DIR_SUMMARY",
                                "duplicate aggregate Dir(s) summary",
                                number,
                            )
                        aggregate.dir_summary = True
                        if not aggregate.file_summary:
                            diagnostics.error(
                                "AGGREGATE_DIR_SUMMARY_BEFORE_FILE_SUMMARY",
                                "aggregate Dir(s) summary appears before "
                                "File(s) summary",
                                number,
                            )
                    elif section.path is None:
                        diagnostics.error(
                            "SUMMARY_OUTSIDE_SECTION",
                            "Dir(s) summary appears outside a section",
                            number,
                        )
                    else:
                        if section.dir_summary:
                            diagnostics.error(
                                "DUPLICATE_SECTION_DIR_SUMMARY",
                                "duplicate section Dir(s) summary",
                                number,
                            )
                        if not section.file_summary:
                            diagnostics.error(
                                "SECTION_DIR_SUMMARY_BEFORE_FILE_SUMMARY",
                                "section Dir(s) summary appears before File(s) summary",
                                number,
                            )
                        section.dir_summary = True
                    continue
                if line.strip() == "File Not Found":
                    self._file_not_found(section, aggregate, number, diagnostics)
                    continue
                if (
                    section.path is not None
                    and section.mountable
                    and not aggregate.active
                ):
                    matched, entry = parse_entry(
                        section.path,
                        line,
                        number,
                        self.date_format,
                        diagnostics,
                    )
                    if matched:
                        if section.file_summary or section.dir_summary:
                            diagnostics.error(
                                "ENTRY_AFTER_SECTION_SUMMARY",
                                "directory entry appears after a section summary",
                                number,
                            )
                            continue
                        if section.file_not_found:
                            diagnostics.error(
                                "ENTRY_WITH_FILE_NOT_FOUND",
                                "directory entry cannot be mixed with File Not Found",
                                number,
                            )
                            continue
                        section.had_entries = True
                        if entry is not None:
                            yield entry
                            if entry.kind is NodeKind.FILE:
                                assert entry.size is not None
                                section.files += 1
                                section.size += entry.size
                                total_files += 1
                                total_size += entry.size
                        continue
                code = "MALFORMED_ENTRY" if resembles_entry(line) else "UNKNOWN_LINE"
                diagnostics.error(
                    code, f"unrecognized meaningful line: {line!r}", number
                )
        except DecodeError as exc:
            diagnostics.error("DECODE_ERROR", str(exc), exc.line_number)

        section.close(diagnostics)
        if not saw_section:
            diagnostics.error(
                "MISSING_SECTION", "listing contains no directory section"
            )
        if not aggregate.active:
            diagnostics.error(
                "MISSING_AGGREGATE_FOOTER", "missing Total Files Listed footer"
            )
        else:
            if not aggregate.file_summary:
                diagnostics.error(
                    "MISSING_AGGREGATE_FILE_SUMMARY",
                    "aggregate footer is missing its File(s) summary",
                )
            if not aggregate.dir_summary:
                diagnostics.error(
                    "MISSING_AGGREGATE_DIR_SUMMARY",
                    "aggregate footer is missing its Dir(s) summary",
                )

    @staticmethod
    def _file_not_found(
        section: SectionState,
        aggregate: AggregateState,
        number: int,
        diagnostics: DiagnosticCollector,
    ) -> None:
        if section.path is None or aggregate.active:
            diagnostics.error(
                "FILE_NOT_FOUND_OUTSIDE_SECTION",
                "File Not Found appears outside a section",
                number,
            )
        elif section.file_summary or section.dir_summary:
            diagnostics.error(
                "FILE_NOT_FOUND_AFTER_SUMMARY",
                "File Not Found appears after a section summary",
                number,
            )
        elif section.had_entries:
            diagnostics.error(
                "FILE_NOT_FOUND_WITH_ENTRIES",
                "File Not Found cannot be mixed with directory entries",
                number,
            )
        elif section.file_not_found:
            diagnostics.error(
                "DUPLICATE_FILE_NOT_FOUND", "duplicate File Not Found marker", number
            )
        else:
            section.file_not_found = True
