"""Typed component and store command registrations for the SnapshotFS CLI."""

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

import click

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

type ComponentArguments = Mapping[str, object]
type SourceFactory = Callable[[ComponentArguments], Source]
type ParserFactory = Callable[[ComponentArguments], Parser]
type StoreCommandFactory = Callable[["CLIRegistry"], click.Group]

_Registration = TypeVar(
    "_Registration", bound="SourceRegistration | ParserRegistration"
)


class RegistryError(ValueError):
    """The CLI component registry cannot be assembled."""


@dataclass(frozen=True)
class SourceRegistration:
    """A named source factory and its Click parameters."""

    name: str
    factory: SourceFactory
    parameters: tuple[click.Parameter, ...] = ()


@dataclass(frozen=True)
class ParserRegistration:
    """A named parser factory and its Click parameters."""

    name: str
    factory: ParserFactory
    parameters: tuple[click.Parameter, ...] = ()


@dataclass(frozen=True)
class StoreCLIRegistration:
    """A named factory for a store-owned CLI command group."""

    name: str
    command_factory: StoreCommandFactory


_COMPONENT_NAMES = "snapshotfs_component_names"


class _ComponentCommand(click.Command):
    """A command whose selected source and parser contribute parameters."""

    def __init__(self, *args: Any, registry: "CLIRegistry", **kwargs: Any) -> None:
        self.registry = registry
        super().__init__(*args, **kwargs)

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        ctx.meta[_COMPONENT_NAMES] = _selected_components(args)
        return super().parse_args(ctx, args)

    def get_params(self, ctx: click.Context) -> list[click.Parameter]:
        base = super().get_params(ctx)
        source_name, parser_name = ctx.meta.get(_COMPONENT_NAMES, (None, None))
        return [
            *base,
            *self.registry.selected_parameters(
                source_name,
                parser_name,
                reserved_names=[parameter.name for parameter in base],
                reserved_options=[
                    option
                    for parameter in base
                    if isinstance(parameter, click.Option)
                    for option in (*parameter.opts, *parameter.secondary_opts)
                ],
            ),
        ]


class CLIRegistry:
    """Explicit source, parser, and store extensions available to the CLI."""

    def __init__(
        self,
        *,
        sources: Iterable[SourceRegistration] = (),
        parsers: Iterable[ParserRegistration] = (),
        stores: Iterable[StoreCLIRegistration] = (),
    ) -> None:
        self._sources: dict[str, SourceRegistration] = {}
        self._parsers: dict[str, ParserRegistration] = {}
        self._stores: dict[str, StoreCLIRegistration] = {}
        for source_registration in sources:
            self.register_source(source_registration)
        for parser_registration in parsers:
            self.register_parser(parser_registration)
        for store_registration in stores:
            self.register_store(store_registration)

    @property
    def source_names(self) -> tuple[str, ...]:
        return tuple(self._sources)

    @property
    def parser_names(self) -> tuple[str, ...]:
        return tuple(self._parsers)

    @property
    def stores(self) -> tuple[StoreCLIRegistration, ...]:
        return tuple(self._stores.values())

    def register_source(self, registration: SourceRegistration) -> None:
        self._register(self._sources, registration, "source")

    def register_parser(self, registration: ParserRegistration) -> None:
        self._register(self._parsers, registration, "parser")

    def register_store(self, registration: StoreCLIRegistration) -> None:
        if not registration.name:
            raise RegistryError("store registration name must not be empty")
        if registration.name in self._stores:
            raise RegistryError(
                f"duplicate store registration name {registration.name!r}"
            )
        self._stores[registration.name] = registration

    def selected_parameters(
        self,
        source_name: str | None,
        parser_name: str | None,
        *,
        reserved_names: Sequence[str] = (),
        reserved_options: Sequence[str] = (),
    ) -> tuple[click.Parameter, ...]:
        selected: tuple[
            tuple[str, SourceRegistration | ParserRegistration | None], ...
        ] = (
            ("source", self._sources.get(source_name) if source_name else None),
            ("parser", self._parsers.get(parser_name) if parser_name else None),
        )
        names = set(reserved_names)
        options = set(reserved_options)
        result: list[click.Parameter] = []
        for kind, registration in selected:
            if registration is None:
                continue
            for parameter in registration.parameters:
                if parameter.name in names:
                    raise RegistryError(
                        f"argument conflict in selected {kind} registration "
                        f"{registration.name!r}: duplicate destination "
                        f"{parameter.name!r}"
                    )
                parameter_options = set(_parameter_options(parameter))
                conflicting_options = parameter_options.intersection(options)
                if conflicting_options:
                    joined = ", ".join(sorted(conflicting_options))
                    raise RegistryError(
                        f"argument conflict in selected {kind} registration "
                        f"{registration.name!r}: reserved option {joined}"
                    )
                names.add(parameter.name)
                options.update(parameter_options)
                result.append(parameter)
        return tuple(result)

    def create_source(self, name: str, arguments: ComponentArguments) -> Source:
        return self._sources[name].factory(arguments)

    def create_parser(self, name: str, arguments: ComponentArguments) -> Parser:
        return self._parsers[name].factory(arguments)

    def component_command(
        self,
        *,
        name: str,
        callback: Callable[..., object],
        parameters: Sequence[click.Parameter] = (),
        help: str | None = None,
    ) -> click.Command:
        """Build a command extended by its selected source and parser."""
        return _ComponentCommand(
            name=name,
            callback=callback,
            params=list(parameters),
            help=help,
            registry=self,
        )

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


def _parameter_options(parameter: click.Parameter) -> tuple[str, ...]:
    if not isinstance(parameter, click.Option):
        return ()
    return (*parameter.opts, *parameter.secondary_opts)


def _selected_components(arguments: Sequence[str]) -> tuple[str | None, str | None]:
    selected: dict[str, str | None] = {"source": None, "parser": None}
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        for name in selected:
            option = f"--{name}"
            if argument == option and index + 1 < len(arguments):
                selected[name] = arguments[index + 1]
                index += 1
            elif argument.startswith(f"{option}="):
                selected[name] = argument.removeprefix(f"{option}=")
        index += 1
    return selected["source"], selected["parser"]


def _complete_encoding(
    _context: click.Context, _parameter: click.Parameter, incomplete: str
) -> list[str]:
    return [item for item in ENCODING_COMPLETIONS if item.startswith(incomplete)]


def default_registry() -> CLIRegistry:
    """Return a fresh registry containing SnapshotFS's built-in components."""
    return CLIRegistry(
        sources=[
            SourceRegistration(
                "file",
                lambda arguments: FileSource(str(arguments["input"])),
                (
                    click.Argument(
                        ["input"], type=click.Path(exists=False, path_type=str)
                    ),
                ),
            )
        ],
        parsers=[
            ParserRegistration(
                "windows-dir",
                lambda arguments: WindowsDirParser(
                    str(arguments["encoding"]), str(arguments["date_format"])
                ),
                (
                    click.Option(
                        ["--encoding"],
                        default="utf-8",
                        show_default=True,
                        shell_complete=_complete_encoding,
                    ),
                    click.Option(
                        ["--date-format"],
                        type=click.Choice([item.value for item in DateFormat]),
                        default="mdy",
                        show_default=True,
                    ),
                ),
            )
        ],
    )


__all__ = [
    "CLIRegistry",
    "ParserRegistration",
    "RegistryError",
    "SourceRegistration",
    "StoreCLIRegistration",
    "default_registry",
]
