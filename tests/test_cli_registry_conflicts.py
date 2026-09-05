import argparse
import io
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from typing import BinaryIO

import pytest

import snapshotfs.cli as cli
from snapshotfs.cli_registry import (
    CLIRegistry,
    ParserRegistration,
    RegistryError,
    SourceRegistration,
)
from snapshotfs.diagnostics import DiagnosticCollector
from snapshotfs.parsers.base import ParseResult


class MemorySource:
    @property
    def uri(self) -> str:
        return "memory:test"

    @property
    def size(self) -> int:
        return 0

    def open(self) -> AbstractContextManager[BinaryIO]:
        return nullcontext(io.BytesIO())


class EmptyParser:
    format_name = "empty"

    def parse(self, stream: BinaryIO) -> ParseResult:
        return ParseResult(iter(()), DiagnosticCollector())


def _registry(
    add_arguments: Callable[[argparse.ArgumentParser], None],
) -> CLIRegistry:
    return CLIRegistry(
        sources=[
            SourceRegistration(
                "conflicting", lambda _args: MemorySource(), add_arguments
            )
        ],
        parsers=[ParserRegistration("empty", lambda _args: EmptyParser())],
    )


@pytest.mark.parametrize(
    "option", ["--json", "--simulate-missing-content", "--source", "--parser", "--help"]
)
def test_registration_cannot_reuse_command_option(option: str) -> None:
    def add_arguments(parser: argparse.ArgumentParser) -> None:
        parser.add_argument(option)

    with pytest.raises(RegistryError, match=r"argument conflict.*conflicting"):
        cli._build_parser(_registry(add_arguments), "conflicting", "empty")


@pytest.mark.parametrize(
    "destination",
    ["as_json", "simulate_missing_content", "source", "parser", "help", "command"],
)
def test_registration_cannot_reuse_command_destination(destination: str) -> None:
    def add_arguments(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--component-value", dest=destination)

    with pytest.raises(
        RegistryError,
        match=rf"argument conflict.*duplicate destination '{destination}'",
    ):
        cli._build_parser(_registry(add_arguments), "conflicting", "empty")


def test_registration_cannot_own_mountpoint_positional() -> None:
    def add_arguments(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("mountpoint")

    with pytest.raises(
        RegistryError,
        match=r"argument conflict.*duplicate destination 'mountpoint'",
    ):
        cli._build_parser(_registry(add_arguments), "conflicting", "empty")
