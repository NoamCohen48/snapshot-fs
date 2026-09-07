import io
import json
import os
import subprocess
import sys
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import BinaryIO

import click
import pytest

import snapshotfs.api as api
from snapshotfs.cli import main
from snapshotfs.cli_registry import (
    CLIRegistry,
    ParserRegistration,
    SourceRegistration,
)
from snapshotfs.diagnostics import DiagnosticCollector
from snapshotfs.parsers.base import ParseResult


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


def test_inspect_command_is_removed(capsys) -> None:
    assert main(["inspect"]) == 2
    assert "No such command 'inspect'" in capsys.readouterr().err


def test_sqlite_create_and_show_tree(
    listing_file: Path, tmp_path: Path, capsys
) -> None:
    artifact = tmp_path / "listing.snapshot"
    assert (
        main(
            [
                "sqlite",
                "create",
                str(artifact),
                "--source",
                "file",
                str(listing_file),
                "--parser",
                "windows-dir",
            ]
        )
        == 0
    )
    assert main(["sqlite", "show", str(artifact)]) == 0
    output = capsys.readouterr().out
    assert "C/" in output
    assert "notes file.txt" in output
    assert "Documents/" in output


def test_sqlite_show_json_preserves_parser_options(
    tmp_path: Path, capsys
) -> None:
    listing = tmp_path / "western.txt"
    artifact = tmp_path / "western.snapshot"
    text = """ Directory of C:\\

13/02/2024 10:00 0 caf\N{LATIN SMALL LETTER E WITH ACUTE}.txt
 1 File(s) 0 bytes
 0 Dir(s) 0 bytes free
 Total Files Listed:
 1 File(s) 0 bytes
 0 Dir(s) 0 bytes free
"""
    listing.write_bytes(text.encode("cp1252"))
    assert (
        main(
            [
                "sqlite",
                "create",
                str(artifact),
                "--source",
                "file",
                str(listing),
                "--parser",
                "windows-dir",
                "--encoding",
                "cp1252",
                "--date-format",
                "dmy",
            ]
        )
        == 0
    )
    assert main(["sqlite", "show", str(artifact), "--json"]) == 0
    document = json.loads(capsys.readouterr().out)
    node = next(item for item in document["nodes"] if item["kind"] == "file")
    assert node["mounted_name"] == "caf\N{LATIN SMALL LETTER E WITH ACUTE}.txt"
    assert node["modified_at"] == "2024-02-13T10:00:00"


def test_create_errors_use_stderr_and_nonzero_status(
    tmp_path: Path, capsys
) -> None:
    listing = tmp_path / "bad.txt"
    listing.write_text("unknown\n")
    assert (
        main(
            [
                "sqlite",
                "create",
                str(tmp_path / "bad.snapshot"),
                "--source",
                "file",
                str(listing),
                "--parser",
                "windows-dir",
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "line 1" in captured.err


def test_memory_mount_creates_store_then_mounts_it(tmp_path: Path, monkeypatch) -> None:
    called: dict[str, object] = {}
    source = MemorySource()
    parser = EmptyParser()
    store = object()

    def fake_create_memory_store(
        actual_source: MemorySource, actual_parser: EmptyParser
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
        sources=[SourceRegistration("test", lambda _arguments: source)],
        parsers=[ParserRegistration("empty", lambda _arguments: parser)],
    )
    monkeypatch.setattr(api, "create_memory_store", fake_create_memory_store)
    monkeypatch.setattr(api, "mount_store", fake_mount_store)
    mountpoint = tmp_path / "mount"
    assert (
        main(
            [
                "memory",
                "mount",
                str(mountpoint),
                "--source",
                "test",
                "--parser",
                "empty",
                "--simulate-missing-content",
            ],
            registry,
        )
        == 0
    )
    assert called == {
        "source": source,
        "parser": parser,
        "store": store,
        "path": str(mountpoint),
        "simulate_missing_content": True,
    }


@pytest.mark.parametrize("missing", ["source", "parser"])
def test_create_requires_explicit_source_and_parser(
    listing_file: Path, tmp_path: Path, missing: str
) -> None:
    arguments = [
        "sqlite",
        "create",
        str(tmp_path / "listing.snapshot"),
        str(listing_file),
    ]
    if missing != "source":
        arguments.extend(["--source", "file"])
    if missing != "parser":
        arguments.extend(["--parser", "windows-dir"])
    assert main(arguments) == 2


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
def test_cli_prints_completion_registration(shell: str, capsys) -> None:
    assert main(["completion", shell]) == 0
    output = capsys.readouterr().out
    assert "_SNAPSHOTFS_COMPLETE" in output
    assert "snapshotfs" in output


@pytest.mark.parametrize(
    ("words", "word_index", "expected"),
    [
        ("snapshotfs s", 1, "sqlite"),
        ("snapshotfs sqlite c", 2, "create"),
        (
            "snapshotfs sqlite create out --source f",
            5,
            "file",
        ),
        (
            "snapshotfs sqlite create out --source file input "
            "--parser windows-dir --enc",
            9,
            "--encoding",
        ),
        (
            "snapshotfs memory mount path --source file input "
            "--parser windows-dir --date-format d",
            10,
            "dmy",
        ),
    ],
)
def test_click_completion(words: str, word_index: int, expected: str) -> None:
    environment = os.environ | {
        "COMP_WORDS": words,
        "COMP_CWORD": str(word_index),
        "_SNAPSHOTFS_COMPLETE": "bash_complete",
    }
    result = subprocess.run(
        [sys.executable, "-m", "snapshotfs.cli"],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    assert expected in result.stdout


def test_selected_file_source_completes_input_paths(tmp_path: Path) -> None:
    (tmp_path / "listing.txt").write_bytes(b"")
    environment = os.environ | {
        "COMP_WORDS": (
            "snapshotfs sqlite create out --source file lis"
        ),
        "COMP_CWORD": "6",
        "_SNAPSHOTFS_COMPLETE": "bash_complete",
    }
    result = subprocess.run(
        [sys.executable, "-m", "snapshotfs.cli"],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout == "file,lis\n"


def test_selected_component_options_appear_in_contextual_help(capsys) -> None:
    assert (
        main(
            [
                "sqlite",
                "create",
                "--source",
                "file",
                "--parser",
                "windows-dir",
                "--help",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "--encoding" in output
    assert "--date-format" in output


def test_custom_component_parameters_are_installed_only_when_selected(
    tmp_path: Path, monkeypatch
) -> None:
    constructed: dict[str, object] = {}

    def make_source(arguments) -> MemorySource:
        constructed["payload"] = arguments["payload"]
        return MemorySource(str(arguments["payload"]).encode())

    def make_parser(arguments) -> EmptyParser:
        constructed["label"] = arguments["label"]
        return EmptyParser()

    registry = CLIRegistry(
        sources=[
            SourceRegistration(
                "custom",
                make_source,
                (click.Option(["--payload"], required=True),),
            ),
            SourceRegistration(
                "other",
                lambda _arguments: MemorySource(),
                (click.Option(["--unused"], required=True),),
            ),
        ],
        parsers=[
            ParserRegistration(
                "custom",
                make_parser,
                (click.Option(["--label"], required=True),),
            )
        ],
    )
    monkeypatch.setattr(api, "mount_store", lambda *_args, **_kwargs: None)
    assert (
        main(
            [
                "memory",
                "mount",
                str(tmp_path / "mount"),
                "--source",
                "custom",
                "--parser",
                "custom",
                "--payload",
                "data",
                "--label",
                "selected",
            ],
            registry,
        )
        == 0
    )
    assert constructed == {"payload": "data", "label": "selected"}
