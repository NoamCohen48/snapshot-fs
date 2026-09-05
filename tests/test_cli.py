import io
import json
import os
import subprocess
import sys
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import BinaryIO

import pytest

import snapshotfs.api as api
from snapshotfs.cli import main
from snapshotfs.cli_registry import (
    CLIRegistry,
    ParserRegistration,
    SourceRegistration,
)
from snapshotfs.diagnostics import DiagnosticCollector
from snapshotfs.model import NodeKind, Observation, ParsedEntry
from snapshotfs.parsers.base import ParseResult

EXPLICIT_INPUT = ["--source", "file", "--parser", "windows-dir"]


class MemorySource:
    def __init__(self, content: bytes = b"") -> None:
        self.content = content

    @property
    def uri(self) -> str:
        return "memory:test"

    @property
    def size(self) -> int:
        return len(self.content)

    def open(self) -> AbstractContextManager[BinaryIO]:
        return nullcontext(io.BytesIO(self.content))


class EmptyParser:
    format_name = "empty"

    def parse(self, stream: BinaryIO) -> ParseResult:
        return ParseResult(iter(()), DiagnosticCollector())


def test_cli_prints_tree(listing_file: Path, capsys) -> None:
    assert main(["inspect", str(listing_file), *EXPLICIT_INPUT]) == 0
    output = capsys.readouterr().out
    assert "C/" in output
    assert "notes file.txt" in output
    assert "Documents/" in output


def test_cli_prints_json_with_naive_source_time(listing_file: Path, capsys) -> None:
    assert main(["inspect", str(listing_file), *EXPLICIT_INPUT, "--json"]) == 0
    document = json.loads(capsys.readouterr().out)
    note = next(
        node for node in document["nodes"] if node["mounted_name"] == "notes file.txt"
    )
    assert note["modified_at"] == "2024-01-02T15:05:00"
    assert not note["modified_at"].endswith("Z")
    assert note["content"] is None
    assert document["diagnostics"] == []


def test_cli_encoding_option(tmp_path: Path, capsys) -> None:
    path = tmp_path / "western.txt"
    text = """ Directory of C:\\\n
01/02/2024 10:00 0 caf\N{LATIN SMALL LETTER E WITH ACUTE}.txt
 1 File(s) 0 bytes
 0 Dir(s) 0 bytes free
 Total Files Listed:
 1 File(s) 0 bytes
 0 Dir(s) 0 bytes free
"""
    path.write_bytes(text.encode("cp1252"))
    assert main(["inspect", str(path), *EXPLICIT_INPUT, "--encoding", "cp1252"]) == 0
    assert "caf\N{LATIN SMALL LETTER E WITH ACUTE}.txt" in capsys.readouterr().out


def test_cli_date_format_option(tmp_path: Path, capsys) -> None:
    path = tmp_path / "dmy.txt"
    path.write_text(
        """ Directory of C:\\
13/02/2024 10:00 0 dated.txt
 1 File(s) 0 bytes
 0 Dir(s) 0 bytes free
 Total Files Listed:
 1 File(s) 0 bytes
 0 Dir(s) 0 bytes free
"""
    )
    assert (
        main(
            [
                "inspect",
                str(path),
                *EXPLICIT_INPUT,
                "--date-format",
                "dmy",
                "--json",
            ]
        )
        == 0
    )
    document = json.loads(capsys.readouterr().out)
    dated = next(
        node for node in document["nodes"] if node["mounted_name"] == "dated.txt"
    )
    assert dated["modified_at"] == "2024-02-13T10:00:00"


def test_cli_errors_use_stderr_and_nonzero_status(tmp_path: Path, capsys) -> None:
    path = tmp_path / "bad.txt"
    path.write_text("unknown\n")
    assert main(["inspect", str(path), *EXPLICIT_INPUT]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "line 1" in captured.err


def test_cli_missing_source_is_contextual(tmp_path: Path, capsys) -> None:
    path = tmp_path / "absent.txt"
    assert main(["inspect", str(path), *EXPLICIT_INPUT]) == 1
    assert str(path) in capsys.readouterr().err


def test_cli_human_and_json_retain_successful_warnings(capsys) -> None:
    class WarningParser:
        format_name = "warning"

        def parse(self, stream: BinaryIO) -> ParseResult:
            diagnostics = DiagnosticCollector()

            def entries():
                diagnostics.warning("TEST_WARNING", "visible warning", 7)
                yield ParsedEntry(
                    ("warning",),
                    NodeKind.DIRECTORY,
                    Observation.SECTION_HEADER,
                    None,
                    None,
                    1,
                )

            return ParseResult(entries(), diagnostics)

    registry = CLIRegistry(
        sources=[SourceRegistration("memory", lambda _args: MemorySource())],
        parsers=[ParserRegistration("warning", lambda _args: WarningParser())],
    )
    arguments = ["inspect", "--source", "memory", "--parser", "warning"]
    assert main(arguments, registry) == 0
    assert "warning: line 7: TEST_WARNING: visible warning" in capsys.readouterr().out

    assert main([*arguments, "--json"], registry) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["diagnostics"] == [
        {
            "severity": "warning",
            "line_number": 7,
            "code": "TEST_WARNING",
            "message": "visible warning",
        }
    ]
    assert document["diagnostic_count"] == 1


def test_mount_cli_creates_memory_store_then_mounts_it(
    tmp_path: Path, monkeypatch
) -> None:
    mountpoint = tmp_path / "mount"
    mountpoint.mkdir()
    called: dict[str, object] = {}
    source = MemorySource()
    parser = EmptyParser()

    store = object()

    def fake_create_memory_store(
        actual_source: MemorySource,
        actual_parser: EmptyParser,
    ) -> object:
        called.update(source=actual_source, parser=actual_parser)
        return store

    def fake_mount_store(
        actual_store: object,
        path: str,
        *,
        simulate_missing_content: bool,
    ) -> None:
        called.update(
            store=actual_store,
            path=path,
            simulate_missing_content=simulate_missing_content,
        )

    registry = CLIRegistry(
        sources=[SourceRegistration("memory", lambda _args: source)],
        parsers=[ParserRegistration("empty", lambda _args: parser)],
    )
    monkeypatch.setattr(api, "create_memory_store", fake_create_memory_store)
    monkeypatch.setattr(api, "mount_store", fake_mount_store)
    assert (
        main(
            [
                "mount",
                "--source",
                "memory",
                "--parser",
                "empty",
                str(mountpoint),
                "--simulate-missing-content",
            ],
            registry,
        )
        == 0
    )
    assert called["source"] is source
    assert called["parser"] is parser
    assert called["store"] is store
    assert called["path"] == str(mountpoint)
    assert called["simulate_missing_content"] is True


def test_inspect_runtime_error_does_not_access_mountpoint(capsys) -> None:
    class FailingParser(EmptyParser):
        def parse(self, stream: BinaryIO) -> ParseResult:
            raise RuntimeError("inspect failed")

    registry = CLIRegistry(
        sources=[SourceRegistration("memory", lambda _args: MemorySource())],
        parsers=[ParserRegistration("failing", lambda _args: FailingParser())],
    )
    assert main(["inspect", "--source", "memory", "--parser", "failing"], registry) == 1
    assert capsys.readouterr().err == "error: inspect failed\n"


@pytest.mark.parametrize("missing", ["source", "parser"])
def test_cli_requires_explicit_source_and_parser(
    listing_file: Path, missing: str
) -> None:
    arguments = ["inspect", str(listing_file)]
    if missing != "source":
        arguments.extend(["--source", "file"])
    if missing != "parser":
        arguments.extend(["--parser", "windows-dir"])
    with pytest.raises(SystemExit):
        main(arguments)


@pytest.mark.parametrize("shell", ["bash", "zsh"])
def test_cli_prints_completion_registration(shell: str, capsys) -> None:
    assert main(["completion", shell]) == 0
    output = capsys.readouterr().out
    assert "_python_argcomplete" in output
    assert "snapshotfs" in output


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("snapshotfs inspect listing.txt --source ", "file"),
        ("snapshotfs inspect listing.txt --source fi", "file"),
        ("snapshotfs inspect listing.txt --source=fi", "--source=file"),
        ("snapshotfs inspect listing.txt --parser ", "windows-dir"),
        ("snapshotfs inspect listing.txt --parser wind", "windows-dir"),
        ("snapshotfs inspect listing.txt --parser=wind", "--parser=windows-dir"),
        (
            "snapshotfs inspect listing.txt --source file --parser windows-dir "
            "--encoding cp12",
            "cp1252",
        ),
        (
            "snapshotfs inspect listing.txt --source file --parser windows-dir "
            "--date-format d",
            "dmy",
        ),
        (
            "snapshotfs inspect listing.txt --source file --parser windows-dir --",
            "--encoding",
        ),
        ("snapshotfs inspect listing.txt --", "--source"),
        ("snapshotfs inspect listing.txt --", "--parser"),
        ("snapshotfs imp", "import"),
        ("snapshotfs import output listing.txt --", "--overwrite"),
        ("snapshotfs inspect-store snapshot.db --", "--json"),
        (
            "snapshotfs mount-store snapshot.db mountpoint --",
            "--simulate-missing-content",
        ),
    ],
)
def test_argcomplete_suggests_flags_and_choices(
    tmp_path: Path, line: str, expected: str
) -> None:
    output = tmp_path / "completions"
    environment = os.environ | {
        "COMP_LINE": line,
        "COMP_POINT": str(len(line)),
        "_ARGCOMPLETE": "1",
        "_ARGCOMPLETE_SHELL": "bash",
        "_ARGCOMPLETE_STDOUT_FILENAME": str(output),
    }
    subprocess.run(
        [sys.executable, "-m", "snapshotfs.cli"],
        env=environment,
        check=True,
    )
    assert expected in output.read_text().split()


@pytest.mark.parametrize(
    ("line", "filename"),
    [
        ("snapshotfs inspect-store arti", "artifact.snapshot"),
        (
            "snapshotfs import output.snapshot --source file --parser windows-dir list",
            "listing.txt",
        ),
    ],
)
def test_argcomplete_suggests_store_and_source_paths(
    tmp_path: Path, line: str, filename: str
) -> None:
    (tmp_path / filename).write_bytes(b"")
    output = tmp_path / "completions"
    environment = os.environ | {
        "COMP_LINE": line,
        "COMP_POINT": str(len(line)),
        "_ARGCOMPLETE": "1",
        "_ARGCOMPLETE_SHELL": "bash",
        "_ARGCOMPLETE_STDOUT_FILENAME": str(output),
    }
    subprocess.run(
        [sys.executable, "-m", "snapshotfs.cli"],
        cwd=tmp_path,
        env=environment,
        check=True,
    )
    assert filename in output.read_text().split()
