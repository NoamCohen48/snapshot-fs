"""Typed component registrations for the SnapshotFS CLI."""

import argparse
from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass
from typing import Protocol, TypeVar, cast

from argcomplete.completers import ChoicesCompleter

from snapshotfs.parsers.base import Parser
from snapshotfs.parsers.windows_dir import DateFormat, WindowsDirParser
from snapshotfs.sources.base import Source
from snapshotfs.sources.file import FileSource

ENCODING_COMPLETIONS = (
    "utf-8",
    "utf-16",
    "utf-16-le",
    "utf-16-be",
    "ascii",
    "latin-1",
    *(f"cp125{index}" for index in range(9)),
)

type SourceFactory = Callable[[argparse.Namespace], Source]
type ParserFactory = Callable[[argparse.Namespace], Parser]
type ArgumentConfigurer = Callable[[argparse.ArgumentParser], None]

_Registration = TypeVar(
    "_Registration", bound="SourceRegistration | ParserRegistration"
)


class _CompletableAction(Protocol):
    completer: object


class RegistryError(ValueError):
    """The CLI component registry cannot be assembled."""


@dataclass(frozen=True)
class SourceRegistration:
    """A named source factory and its CLI argument definitions."""

    name: str
    factory: SourceFactory
    add_arguments: ArgumentConfigurer | None = None


@dataclass(frozen=True)
class ParserRegistration:
    """A named parser factory and its CLI argument definitions."""

    name: str
    factory: ParserFactory
    add_arguments: ArgumentConfigurer | None = None


class CLIRegistry:
    """Explicit source and parser implementations available to the CLI."""

    def __init__(
        self,
        *,
        sources: Iterable[SourceRegistration] = (),
        parsers: Iterable[ParserRegistration] = (),
    ) -> None:
        self._sources: dict[str, SourceRegistration] = {}
        self._parsers: dict[str, ParserRegistration] = {}
        for source_registration in sources:
            self.register_source(source_registration)
        for parser_registration in parsers:
            self.register_parser(parser_registration)

    @property
    def source_names(self) -> tuple[str, ...]:
        return tuple(self._sources)

    @property
    def parser_names(self) -> tuple[str, ...]:
        return tuple(self._parsers)

    def register_source(self, registration: SourceRegistration) -> None:
        self._register(self._sources, registration, "source")

    def register_parser(self, registration: ParserRegistration) -> None:
        self._register(self._parsers, registration, "parser")

    def add_selected_arguments(
        self,
        parser: argparse.ArgumentParser,
        source_name: str | None,
        parser_name: str | None,
        *,
        reserved_destinations: Collection[str] = (),
        reserved_option_strings: Collection[str] = (),
    ) -> None:
        selected: tuple[
            tuple[str, SourceRegistration | ParserRegistration | None], ...
        ] = (
            ("source", self._sources.get(source_name) if source_name else None),
            ("parser", self._parsers.get(parser_name) if parser_name else None),
        )
        for kind, registration in selected:
            if registration is None or registration.add_arguments is None:
                continue
            existing_actions = {id(action) for action in parser._actions}
            existing_destinations = {
                *(action.dest for action in parser._actions),
                *reserved_destinations,
            }
            try:
                registration.add_arguments(parser)
            except argparse.ArgumentError as exc:
                raise RegistryError(
                    f"argument conflict in selected {kind} registration "
                    f"{registration.name!r}: {exc}"
                ) from exc
            new_destinations: set[str] = set()
            for action in parser._actions:
                if id(action) in existing_actions:
                    continue
                if (
                    action.dest in existing_destinations
                    or action.dest in new_destinations
                ):
                    raise RegistryError(
                        f"argument conflict in selected {kind} registration "
                        f"{registration.name!r}: duplicate destination {action.dest!r}"
                    )
                conflicting_options = set(action.option_strings).intersection(
                    reserved_option_strings
                )
                if conflicting_options:
                    options = ", ".join(sorted(conflicting_options))
                    raise RegistryError(
                        f"argument conflict in selected {kind} registration "
                        f"{registration.name!r}: reserved option {options}"
                    )
                new_destinations.add(action.dest)

    def create_source(self, name: str, args: argparse.Namespace) -> Source:
        return self._sources[name].factory(args)

    def create_parser(self, name: str, args: argparse.Namespace) -> Parser:
        return self._parsers[name].factory(args)

    @staticmethod
    def _register(
        registrations: dict[str, _Registration],
        registration: _Registration,
        kind: str,
    ) -> None:
        if not registration.name:
            raise RegistryError(f"{kind} registration name must not be empty")
        if registration.name in registrations:
            raise RegistryError(
                f"duplicate {kind} registration name {registration.name!r}"
            )
        registrations[registration.name] = registration


def _add_windows_dir_arguments(parser: argparse.ArgumentParser) -> None:
    encoding = parser.add_argument("--encoding", default="utf-8")
    cast(_CompletableAction, encoding).completer = ChoicesCompleter(
        {choice: choice for choice in ENCODING_COMPLETIONS}
    )
    parser.add_argument(
        "--date-format", choices=[item.value for item in DateFormat], default="mdy"
    )


def _add_file_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("input")


def default_registry() -> CLIRegistry:
    """Return a fresh registry containing SnapshotFS's built-in components."""
    return CLIRegistry(
        sources=[
            SourceRegistration(
                "file", lambda args: FileSource(args.input), _add_file_arguments
            )
        ],
        parsers=[
            ParserRegistration(
                "windows-dir",
                lambda args: WindowsDirParser(args.encoding, args.date_format),
                _add_windows_dir_arguments,
            )
        ],
    )


__all__ = [
    "CLIRegistry",
    "ParserRegistration",
    "RegistryError",
    "SourceRegistration",
    "default_registry",
]
