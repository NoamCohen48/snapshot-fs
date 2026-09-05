"""Grammar matching and value parsing for Windows ``dir /s`` records."""

import re
from datetime import datetime
from enum import StrEnum
from pathlib import PureWindowsPath

from snapshotfs.diagnostics import DiagnosticCollector
from snapshotfs.model import NodeKind, Observation, ParsedEntry
from snapshotfs.parsers.windows_dir.paths import to_mounted_path

_HEADER = re.compile(r"^\s*Directory of\s+(.+?)\s*$")
_ENTRY = re.compile(
    r"^\s*(?P<date>\d{1,4}(?P<separator>[/.-])\d{1,2}"
    r"(?P=separator)\d{1,4})\s+(?P<time>\d{1,2}:\d{2})"
    r"(?:\s+(?P<meridiem>[AP]M))?\s+"
    r"(?:(?P<directory><DIR>) {10}|(?P<size>[\d,]+) )(?P<name>.+)$"
)
_FILE_SUMMARY = re.compile(r"^\s*([\d,]+) File\(s\)\s+([\d,]+) bytes\s*$")
_DIR_SUMMARY = re.compile(r"^\s*([\d,]+) Dir\(s\)\s+([\d,]+) bytes free\s*$")
_VOLUME = re.compile(
    r"^\s*(?:Volume in drive .+|Volume Serial Number is [0-9A-Fa-f-]+)\s*$"
)


class DateFormat(StrEnum):
    MDY = "mdy"
    DMY = "dmy"
    YMD = "ymd"


def header_path(line: str) -> str | None:
    match = _HEADER.fullmatch(line)
    return match.group(1) if match else None


def file_summary(line: str) -> tuple[str, str] | None:
    match = _FILE_SUMMARY.fullmatch(line)
    return (match.group(1), match.group(2)) if match else None


def dir_summary(line: str) -> tuple[str, str] | None:
    match = _DIR_SUMMARY.fullmatch(line)
    return (match.group(1), match.group(2)) if match else None


def is_volume(line: str) -> bool:
    return _VOLUME.fullmatch(line) is not None


def resembles_entry(line: str) -> bool:
    return re.match(r"^\s*\d", line) is not None


def parse_entry(
    section: PureWindowsPath,
    line: str,
    line_number: int,
    date_format: DateFormat,
    diagnostics: DiagnosticCollector,
) -> tuple[bool, ParsedEntry | None]:
    match = _ENTRY.fullmatch(line)
    if match is None:
        return False, None
    modified = _parse_datetime(
        match.group("date"),
        match.group("time"),
        match.group("meridiem"),
        date_format,
        line_number,
        diagnostics,
    )
    name = match.group("name")
    if modified is None or name in {".", ".."}:
        return True, None
    if "\x00" in name or "/" in name or "\\" in name or ":" in name:
        diagnostics.error(
            "INVALID_ENTRY_NAME",
            "entry name contains NUL, a path separator, or an unsupported colon",
            line_number,
        )
        return True, None
    if match.group("directory") is not None:
        kind = NodeKind.DIRECTORY
        observation = Observation.DIRECTORY_ENTRY
        size = None
    else:
        size_text = match.group("size")
        assert size_text is not None
        size = parse_integer(size_text)
        if size is None:
            diagnostics.error(
                "INVALID_SIZE", f"invalid file size {size_text!r}", line_number
            )
            return True, None
        kind = NodeKind.FILE
        observation = Observation.FILE_ENTRY
    return True, ParsedEntry(
        to_mounted_path(section / name),
        kind,
        observation,
        size,
        modified,
        line_number,
    )


def parse_integer(text: str) -> int | None:
    if not re.fullmatch(r"\d{1,3}(?:,\d{3})*|\d+", text):
        return None
    try:
        return int(text.replace(",", ""))
    except ValueError:
        return None


def valid_section_path(raw_path: str) -> bool:
    if not re.fullmatch(r"[A-Za-z]:\\.*", raw_path):
        return False
    remainder = raw_path[3:]
    if not remainder:
        return True
    components = remainder.split("\\")
    return (
        all(component not in {"", ".", ".."} for component in components)
        and all(":" not in component for component in components)
    )


def _parse_datetime(
    date_text: str,
    time_text: str,
    meridiem: str | None,
    date_format: DateFormat,
    line_number: int,
    diagnostics: DiagnosticCollector,
) -> datetime | None:
    tokens = re.split(r"[/.-]", date_text)
    parts = [int(part) for part in tokens]
    positions = {
        DateFormat.MDY: (2, 0, 1),
        DateFormat.DMY: (2, 1, 0),
        DateFormat.YMD: (0, 1, 2),
    }[date_format]
    year, month, day = (parts[index] for index in positions)
    if len(tokens[positions[0]]) != 4:
        diagnostics.error(
            "TWO_DIGIT_YEAR", "entry dates require a four-digit year", line_number
        )
        return None
    hour, minute = (int(part) for part in time_text.split(":"))
    if meridiem is not None:
        if not 1 <= hour <= 12:
            diagnostics.error("INVALID_TIME", "12-hour time must use 1-12", line_number)
            return None
        hour = hour % 12 + (12 if meridiem == "PM" else 0)
    elif not 0 <= hour <= 23:
        diagnostics.error("INVALID_TIME", "24-hour time must use 0-23", line_number)
        return None
    try:
        return datetime(year, month, day, hour, minute)
    except ValueError as exc:
        diagnostics.error("INVALID_DATETIME", str(exc), line_number)
        return None
