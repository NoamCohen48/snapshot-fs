import argparse
import io
import json
from contextlib import AbstractContextManager, nullcontext
from typing import BinaryIO

import pytest

import snapshotfs.cli as cli
from snapshotfs.cli import main
from snapshotfs.cli_registry import (
    CLIRegistry,
    ParserRegistration,
    RegistryError,
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


def test_custom_registrations_own_factory_options(capsys) -> None:
    constructed: dict[str, object] = {}

    def add_source_arguments(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--payload", required=True)

    def make_source(args: argparse.Namespace) -> MemorySource:
        source = MemorySource(args.payload.encode())
        constructed["source"] = source
        return source

    def add_parser_arguments(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--label", required=True)

    def make_parser(args: argparse.Namespace) -> EmptyParser:
        parser = EmptyParser()
        constructed["parser"] = parser
        constructed["label"] = args.label
        return parser

    registry = CLIRegistry(
        sources=[
            SourceRegistration("custom-source", make_source, add_source_arguments)
        ],
        parsers=[
            ParserRegistration("custom-parser", make_parser, add_parser_arguments)
        ],
    )
    assert (
        main(
            [
                "inspect",
                "--source",
                "custom-source",
                "--parser",
                "custom-parser",
                "--payload",
                "data",
                "--label",
                "selected",
                "--json",
            ],
            registry,
        )
        == 0
    )
    assert isinstance(constructed["source"], MemorySource)
    assert isinstance(constructed["parser"], EmptyParser)
    assert constructed["label"] == "selected"
    document = json.loads(capsys.readouterr().out)
    assert document["snapshot"]["source_format"] == "empty"
    assert len(document["nodes"]) == 1


def test_registry_names_define_cli_choices() -> None:
    registry = CLIRegistry(
        sources=[SourceRegistration("custom-source", lambda _args: MemorySource())],
        parsers=[ParserRegistration("custom-parser", lambda _args: EmptyParser())],
    )
    parser = cli._build_parser(registry, "custom-source", "custom-parser")
    args = parser.parse_args(
        [
            "inspect",
            "--source",
            "custom-source",
            "--parser",
            "custom-parser",
        ]
    )
    assert args.source == "custom-source"
    assert args.parser == "custom-parser"
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "inspect",
                "--source",
                "file",
                "--parser",
                "windows-dir",
            ]
        )


def test_registry_rejects_duplicate_names() -> None:
    registration = SourceRegistration("same", lambda _args: MemorySource())
    with pytest.raises(
        RegistryError, match="duplicate source registration name 'same'"
    ):
        CLIRegistry(sources=[registration, registration])


def test_unselected_required_component_arguments_are_not_installed(capsys) -> None:
    def add_selected_source(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--source-value", required=True)

    def add_unselected_source(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--unused-source", required=True)

    def add_selected_parser(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--parser-value", required=True)

    def add_unselected_parser(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--unused-parser", required=True)

    registry = CLIRegistry(
        sources=[
            SourceRegistration(
                "selected", lambda _args: MemorySource(), add_selected_source
            ),
            SourceRegistration(
                "other", lambda _args: MemorySource(), add_unselected_source
            ),
        ],
        parsers=[
            ParserRegistration(
                "selected", lambda _args: EmptyParser(), add_selected_parser
            ),
            ParserRegistration(
                "other", lambda _args: EmptyParser(), add_unselected_parser
            ),
        ],
    )
    assert (
        main(
            [
                "inspect",
                "--source",
                "selected",
                "--parser",
                "selected",
                "--source-value",
                "source",
                "--parser-value",
                "parser",
                "--json",
            ],
            registry,
        )
        == 0
    )
    document = json.loads(capsys.readouterr().out)
    assert document["snapshot"]["source_uri"] == "memory:test"


def test_unselected_registrations_can_reuse_option_names() -> None:
    def add_shared(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--credential", required=True)

    registry = CLIRegistry(
        sources=[
            SourceRegistration("first", lambda _args: MemorySource(), add_shared),
            SourceRegistration("second", lambda _args: MemorySource(), add_shared),
        ],
        parsers=[ParserRegistration("empty", lambda _args: EmptyParser())],
    )
    parser = cli._build_parser(registry, "first", "empty")
    args = parser.parse_args(
        [
            "inspect",
            "--source",
            "first",
            "--parser",
            "empty",
            "--credential",
            "secret",
        ]
    )
    assert args.credential == "secret"


def test_registry_reports_selected_source_parser_option_conflict() -> None:
    def add_conflicting_option(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--shared")

    registry = CLIRegistry(
        sources=[
            SourceRegistration(
                "conflicting", lambda _args: MemorySource(), add_conflicting_option
            )
        ],
        parsers=[
            ParserRegistration(
                "conflicting-parser",
                lambda _args: EmptyParser(),
                add_conflicting_option,
            )
        ],
    )
    with pytest.raises(
        RegistryError,
        match=(
            r"argument conflict in selected parser registration "
            r"'conflicting-parser'.*--shared"
        ),
    ):
        cli._build_parser(registry, "conflicting", "conflicting-parser")


def test_completion_selector_tolerates_incomplete_shell_input(monkeypatch) -> None:
    line = (
        "snapshotfs inspect --source custom-source --parser custom-parser "
        "--label 'unfinished"
    )
    monkeypatch.setenv("_ARGCOMPLETE", "1")
    monkeypatch.setenv("COMP_LINE", line)
    monkeypatch.setenv("COMP_POINT", str(len(line)))
    registry = CLIRegistry(
        sources=[SourceRegistration("custom-source", lambda _args: MemorySource())],
        parsers=[ParserRegistration("custom-parser", lambda _args: EmptyParser())],
    )
    assert cli._completion_arguments(registry) == [
        "inspect",
        "--source",
        "custom-source",
        "--parser",
        "custom-parser",
    ]


@pytest.mark.parametrize(
    "selector", ["--source", "--source=fi", "--parser", "--parser=wind"]
)
def test_normal_selector_parsing_remains_strict(selector: str) -> None:
    if "=" in selector:
        arguments = ["inspect", selector]
    else:
        arguments = ["inspect", selector, "partial"]
    with pytest.raises(SystemExit):
        main(arguments)
