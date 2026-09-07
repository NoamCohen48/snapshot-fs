import click
import pytest

from snapshotfs.cli import build_cli, main
from snapshotfs.cli_registry import (
    CLIRegistry,
    ParserRegistration,
    RegistryError,
    SourceRegistration,
    StoreCLIRegistration,
)


def test_registry_rejects_duplicate_component_names() -> None:
    source = SourceRegistration("same", lambda _arguments: None)  # type: ignore[arg-type]
    parser = ParserRegistration("same", lambda _arguments: None)  # type: ignore[arg-type]
    with pytest.raises(RegistryError, match="duplicate source registration"):
        CLIRegistry(sources=[source, source])
    with pytest.raises(RegistryError, match="duplicate parser registration"):
        CLIRegistry(parsers=[parser, parser])


def test_registered_store_owns_commands_and_subcommands(capsys) -> None:
    def commands(_registry: CLIRegistry) -> click.Group:
        group = click.Group(help="Remote HTTP snapshots.")

        @click.command()
        @click.option("--url", required=True)
        def mount(url: str) -> None:
            click.echo(url)

        group.add_command(mount)
        return group

    registry = CLIRegistry(
        stores=[StoreCLIRegistration("http", commands)],
    )
    assert main(["http", "mount", "--url", "https://example.test"], registry) == 0
    assert capsys.readouterr().out == "https://example.test\n"


def test_registered_store_can_build_component_aware_commands(capsys) -> None:
    registry = CLIRegistry(
        sources=[
            SourceRegistration(
                "custom-source",
                lambda arguments: arguments["payload"],  # type: ignore[return-value]
                (click.Option(["--payload"], required=True),),
            )
        ],
        parsers=[
            ParserRegistration(
                "custom-parser",
                lambda _arguments: None,  # type: ignore[return-value]
            )
        ],
    )

    def commands(active_registry: CLIRegistry) -> click.Group:
        group = click.Group()

        def create(**arguments: object) -> None:
            click.echo(arguments["payload"])

        group.add_command(
            active_registry.component_command(
                name="create",
                callback=create,
                parameters=[
                    click.Option(
                        ["--source"],
                        type=click.Choice(active_registry.source_names),
                        required=True,
                    ),
                    click.Option(
                        ["--parser"],
                        type=click.Choice(active_registry.parser_names),
                        required=True,
                    ),
                ],
            )
        )
        return group

    registry.register_store(StoreCLIRegistration("custom", commands))
    assert (
        main(
            [
                "custom",
                "create",
                "--source",
                "custom-source",
                "--parser",
                "custom-parser",
                "--payload",
                "data",
            ],
            registry,
        )
        == 0
    )
    assert capsys.readouterr().out == "data\n"


def test_keyboard_interrupt_returns_130(capsys) -> None:
    def commands(_registry: CLIRegistry) -> click.Group:
        group = click.Group()

        @click.command()
        def mount() -> None:
            raise KeyboardInterrupt

        group.add_command(mount)
        return group

    registry = CLIRegistry(stores=[StoreCLIRegistration("interrupt", commands)])
    assert main(["interrupt", "mount"], registry) == 130
    assert capsys.readouterr().err == "\nAborted!\n"


def test_registered_store_appears_in_root_help(capsys) -> None:
    registry = CLIRegistry(
        stores=[StoreCLIRegistration("custom", lambda _registry: click.Group())]
    )
    assert main(["--help"], registry) == 0
    assert "custom" in capsys.readouterr().out


def test_store_names_cannot_conflict_with_builtins() -> None:
    for name in ("sqlite", "memory", "completion"):
        registry = CLIRegistry(
            stores=[StoreCLIRegistration(name, lambda _registry: click.Group())]
        )
        with pytest.raises(RegistryError, match="duplicate or reserved"):
            build_cli(registry)


def test_unselected_registrations_can_reuse_options() -> None:
    shared = (click.Option(["--credential"], required=True),)
    registry = CLIRegistry(
        sources=[
            SourceRegistration("first", lambda _arguments: None, shared),  # type: ignore[arg-type]
            SourceRegistration("second", lambda _arguments: None, shared),  # type: ignore[arg-type]
        ]
    )
    assert registry.selected_parameters("first", None) == shared


def test_selected_registration_conflicts_are_rejected() -> None:
    registry = CLIRegistry(
        sources=[
            SourceRegistration(
                "source",
                lambda _arguments: None,  # type: ignore[arg-type]
                (click.Option(["--shared"]),),
            )
        ],
        parsers=[
            ParserRegistration(
                "parser",
                lambda _arguments: None,  # type: ignore[arg-type]
                (click.Option(["--shared"]),),
            )
        ],
    )
    with pytest.raises(RegistryError, match=r"parser.*duplicate destination 'shared'"):
        registry.selected_parameters("source", "parser")
