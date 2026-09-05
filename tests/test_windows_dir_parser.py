import io
from datetime import datetime
from types import SimpleNamespace

import pytest

from snapshotfs.model import NodeKind, Observation
from snapshotfs.parsers.windows_dir import WindowsDirParser


def parse(text: str, date_format: str = "mdy", encoding: str = "utf-8"):
    result = WindowsDirParser(encoding, date_format).parse(
        io.BytesIO(text.encode(encoding))
    )
    entries = tuple(result.entries)
    return SimpleNamespace(
        entries=entries,
        diagnostics=result.diagnostics,
        diagnostic_count=result.diagnostic_count,
    )


def codes(result: object) -> set[str]:
    return {item.code for item in result.diagnostics}  # type: ignore[attr-defined]


def test_happy_path_emits_headers_files_directories_and_spaces(
    listing_text: str,
) -> None:
    result = parse(listing_text)

    assert result.diagnostics == ()
    assert len(result.entries) == 5
    assert result.entries[0].observation is Observation.SECTION_HEADER
    directory = result.entries[1]
    assert directory.kind is NodeKind.DIRECTORY
    assert directory.path[-1] == "Documents"
    file = result.entries[2]
    assert file.path[-1] == "notes file.txt"
    assert file.path[:2] == ("C", "Users")
    assert file.size == 1234
    assert file.modified_local == datetime(2024, 1, 2, 15, 5)


def test_windows_drive_is_an_uppercase_first_level_component() -> None:
    text = """ Directory of c:\\
 0 File(s) 0 bytes
 0 Dir(s) 0 bytes free
 Total Files Listed:
 0 File(s) 0 bytes
 0 Dir(s) 0 bytes free
"""
    result = parse(text)
    assert result.diagnostics == ()
    assert result.entries[0].path == ("C",)


def test_empty_section_and_file_not_found_are_valid() -> None:
    text = """ Directory of C:\\empty
File Not Found
 0 File(s) 0 bytes
 0 Dir(s) 1 bytes free
 Total Files Listed:
 0 File(s) 0 bytes
 0 Dir(s) 1 bytes free
"""
    result = parse(text)

    assert result.diagnostics == ()
    assert len(result.entries) == 1


def test_parser_accepts_initial_utf8_sig_bom() -> None:
    text = """ Directory of C:\\\n
 0 File(s) 0 bytes
 0 Dir(s) 0 bytes free
 Total Files Listed:
 0 File(s) 0 bytes
 0 Dir(s) 0 bytes free
"""
    assert parse(text, encoding="utf-8-sig").diagnostics == ()


def test_parser_treats_interior_utf8_sig_bom_as_content() -> None:
    text = """ Directory of C:\\\n
 0 File(s) 0 bytes
 0 Dir(s) 0 bytes free
\ufeff Total Files Listed:
 0 File(s) 0 bytes
 0 Dir(s) 0 bytes free
"""
    result = parse(text, encoding="utf-8-sig")
    unknown = next(item for item in result.diagnostics if item.code == "UNKNOWN_LINE")
    assert unknown.line_number == 5
    assert "\\ufeff Total Files Listed" in ascii(unknown.message)


@pytest.mark.parametrize(
    ("date_format", "date", "expected"),
    [
        ("mdy", "12/31/2024", datetime(2024, 12, 31, 0, 1)),
        ("dmy", "31-12-2024", datetime(2024, 12, 31, 12, 1)),
        ("ymd", "2024.12.31", datetime(2024, 12, 31, 23, 1)),
    ],
)
def test_date_orders_separators_and_times(
    date_format: str, date: str, expected: datetime
) -> None:
    suffix = "12:01 AM" if date_format == "mdy" else "12:01 PM"
    if date_format == "ymd":
        suffix = "23:01"
    text = f""" Directory of C:\\\n
{date} {suffix} 0 empty.txt
 1 File(s) 0 bytes
 0 Dir(s) 0 bytes free
 Total Files Listed:
 1 File(s) 0 bytes
 0 Dir(s) 0 bytes free
"""
    result = parse(text, date_format)

    assert result.diagnostics == ()
    assert result.entries[1].modified_local == expected


@pytest.mark.parametrize(
    ("line", "code"),
    [
        ("01/02/24 10:00 1 bad.txt", "TWO_DIGIT_YEAR"),
        ("02/30/2024 10:00 1 bad.txt", "INVALID_DATETIME"),
        ("01/02/2024 24:00 1 bad.txt", "INVALID_TIME"),
        ("01/02/2024 10:00 1,2 bad.txt", "INVALID_SIZE"),
    ],
)
def test_invalid_entry_metadata_is_diagnostic(line: str, code: str) -> None:
    text = f""" Directory of C:\\\n
{line}
 0 File(s) 0 bytes
 0 Dir(s) 0 bytes free
 Total Files Listed:
 0 File(s) 0 bytes
 0 Dir(s) 0 bytes free
"""
    assert code in codes(parse(text))


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("missing_footer", "MISSING_AGGREGATE_FOOTER"),
        ("missing_section_file", "MISSING_SECTION_FILE_SUMMARY"),
        ("section_count", "SECTION_FILE_TOTAL_MISMATCH"),
        ("aggregate_count", "AGGREGATE_FILE_TOTAL_MISMATCH"),
        ("aggregate_bytes", "AGGREGATE_FILE_TOTAL_MISMATCH"),
    ],
)
def test_completeness_and_totals_fail_closed(
    listing_text: str, mutation: str, code: str
) -> None:
    text = listing_text
    if mutation == "missing_footer":
        text = text.split("     Total Files Listed:")[0]
    elif mutation == "missing_section_file":
        text = text.replace("               1 File(s)          1,234 bytes\n", "", 1)
    elif mutation == "section_count":
        text = text.replace("1 File(s)          1,234", "2 File(s)          1,234", 1)
    elif mutation == "aggregate_count":
        text = text.replace("2 File(s)          1,242", "3 File(s)          1,242")
    else:
        text = text.replace("2 File(s)          1,242", "2 File(s)          1,243")
    assert code in codes(parse(text))


@pytest.mark.parametrize(
    ("summary", "code"),
    [
        (" 0 File(s) 0 bytes\n", "MISSING_AGGREGATE_DIR_SUMMARY"),
        (" 0 Dir(s) 0 bytes free\n", "MISSING_AGGREGATE_FILE_SUMMARY"),
    ],
)
def test_each_aggregate_summary_is_required(summary: str, code: str) -> None:
    text = f""" Directory of C:\\\n
 0 File(s) 0 bytes
 0 Dir(s) 0 bytes free
 Total Files Listed:
{summary}"""
    assert code in codes(parse(text))


def test_unknown_and_localized_lines_have_line_numbers() -> None:
    result = parse("Directorio de C:\\\n")

    assert result.diagnostics[0].code == "UNKNOWN_LINE"
    assert result.diagnostics[0].line_number == 1


def test_entry_after_section_summary_invalidates_summary() -> None:
    text = """ Directory of C:\\\n
 0 File(s) 0 bytes
01/02/2024 10:00 1 late.txt
 0 Dir(s) 0 bytes free
 Total Files Listed:
 1 File(s) 1 bytes
 0 Dir(s) 0 bytes free
"""
    result_codes = codes(parse(text))
    assert "ENTRY_AFTER_SECTION_SUMMARY" in result_codes


@pytest.mark.parametrize(
    ("records", "code"),
    [
        (
            "File Not Found\n01/02/2024 10:00 0 file.txt\n",
            "ENTRY_WITH_FILE_NOT_FOUND",
        ),
        (
            "01/02/2024 10:00 0 file.txt\nFile Not Found\n",
            "FILE_NOT_FOUND_WITH_ENTRIES",
        ),
    ],
)
def test_file_not_found_cannot_be_mixed_with_entries(records: str, code: str) -> None:
    text = f""" Directory of C:\\\n
{records} 1 File(s) 0 bytes
 0 Dir(s) 0 bytes free
 Total Files Listed:
 1 File(s) 0 bytes
 0 Dir(s) 0 bytes free
"""
    assert code in codes(parse(text))


def test_section_record_state_resets_for_next_header() -> None:
    text = """ Directory of C:\\empty
File Not Found
 0 File(s) 0 bytes
 0 Dir(s) 0 bytes free
 Directory of C:\\full
01/02/2024 10:00 1 file.txt
 1 File(s) 1 bytes
 0 Dir(s) 0 bytes free
 Total Files Listed:
 1 File(s) 1 bytes
 0 Dir(s) 0 bytes free
"""
    assert parse(text).diagnostics == ()


def test_section_summaries_must_be_ordered() -> None:
    text = """ Directory of C:\\\n
 0 Dir(s) 0 bytes free
 0 File(s) 0 bytes
 Total Files Listed:
 0 File(s) 0 bytes
 0 Dir(s) 0 bytes free
"""
    result_codes = codes(parse(text))
    assert "SECTION_DIR_SUMMARY_BEFORE_FILE_SUMMARY" in result_codes


def test_parser_is_lazy() -> None:
    class TrackingStream(io.BytesIO):
        reads = 0

        def read(self, size: int | None = -1) -> bytes:
            self.reads += 1
            return super().read(size)

    stream = TrackingStream(
        b" Directory of C:\\\n 0 File(s) 0 bytes\n 0 Dir(s) 0 bytes free\n"
    )
    result = WindowsDirParser().parse(stream)
    assert stream.reads == 0
    assert next(result.entries).observation is Observation.SECTION_HEADER
    assert stream.reads > 0


@pytest.mark.parametrize(
    "name", ["bad/name", r"bad\name", "bad\x00name", "file:stream"]
)
def test_unsafe_entry_names_are_rejected(name: str) -> None:
    text = f""" Directory of C:\\\n
01/02/2024 10:00 0 {name}
 0 File(s) 0 bytes
 0 Dir(s) 0 bytes free
 Total Files Listed:
 0 File(s) 0 bytes
 0 Dir(s) 0 bytes free
"""
    assert "INVALID_ENTRY_NAME" in codes(parse(text))


@pytest.mark.parametrize(
    "path",
    [
        r"C:\\double",
        r"C:\\parent\\child",
        "C:\\trailing\\",
        r"C:\file:stream",
        r"C:\safe\..\escape",
        r"relative\file",
        r"\\server\share\file",
    ],
)
def test_section_paths_reject_empty_components_and_ads(path: str) -> None:
    text = f""" Directory of {path}
 0 File(s) 0 bytes
 0 Dir(s) 0 bytes free
 Total Files Listed:
 0 File(s) 0 bytes
 0 Dir(s) 0 bytes free
"""
    result = parse(text)
    assert "INVALID_SECTION_PATH" in codes(result)
    assert result.entries == ()


@pytest.mark.parametrize(("marker", "padding"), [("0", " "), ("<DIR>", " " * 10)])
def test_entry_grammar_preserves_filename_leading_spaces(
    marker: str, padding: str
) -> None:
    text = f""" Directory of C:\\\n
01/02/2024 10:00 {marker}{padding}  leading name
 1 File(s) 0 bytes
 0 Dir(s) 0 bytes free
 Total Files Listed:
 1 File(s) 0 bytes
 0 Dir(s) 0 bytes free
"""
    if marker == "<DIR>":
        text = text.replace("1 File(s)", "0 File(s)")
    result = parse(text)
    assert result.diagnostics == ()
    assert result.entries[1].path[-1] == "  leading name"


def test_diagnostics_are_bounded() -> None:
    text = "\n".join(["unknown"] * 1005)
    result = parse(text)

    assert len(result.diagnostics) == 1000
    assert result.diagnostic_count > len(result.diagnostics)


def test_parser_reports_oversized_line_as_decode_error() -> None:
    result = WindowsDirParser().parse(io.BytesIO(b"x" * (1024 * 1024 + 1)))
    tuple(result.entries)
    assert "DECODE_ERROR" in codes(result)
