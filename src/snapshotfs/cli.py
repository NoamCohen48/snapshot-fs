"""SnapshotFS command-line interface."""

import json
import sys
from collections.abc import Mapping, Sequence
from contextlib import closing

import click
from click.shell_completion import get_completion_class

import snapshotfs.api as api
from snapshotfs.cli_output import json_document, print_tree
from snapshotfs.cli_registry import (
    CLIRegistry,
    RegistryError,
    StoreCLIRegistration,
    default_registry,
)
from snapshotfs.import_service import ImportFailure
from snapshotfs.parsers.base import Parser
from snapshotfs.sources import SourceError
from snapshotfs.sources.base import Source


def main(argv: Sequence[str] | None = None, registry: CLIRegistry | None = None) -> int:
    """Run the CLI and return its process exit status."""
    try:
        command = build_cli(registry if registry is not None else default_registry())
        result = command.main(
            args=list(argv) if argv is not None else None,
            prog_name="snapshotfs",
            standalone_mode=False,
        )
    except click.ClickException as exc:
        exc.show(file=sys.stderr)
        return exc.exit_code
    except ImportFailure as exc:
        from snapshotfs.cli_output import format_diagnostic

        for diagnostic in exc.diagnostics:
            click.echo(format_diagnostic(diagnostic), err=True)
        if exc.diagnostic_count > len(exc.diagnostics):
            click.echo(
                f"{exc.diagnostic_count} diagnostics observed; "
                f"showing first {len(exc.diagnostics)}",
                err=True,
            )
        return 1
    except SourceError as exc:
        click.echo(f"error: {exc}", err=True)
        return 1
    except api.FuseUnavailableError:
        click.echo(
            "error: FUSE support is unavailable; install it with "
            "`uv sync --extra fuse`",
            err=True,
        )
        return 1
    except click.Abort:
        click.echo("Aborted!", err=True)
        return 130
    except KeyboardInterrupt:
        return 130
    except (OSError, RuntimeError, RegistryError) as exc:
        click.echo(f"error: {exc}", err=True)
        return 1
    return result if isinstance(result, int) else 0


def build_cli(registry: CLIRegistry) -> click.Group:
    """Build a root command from built-in and registered store command groups."""
    root = click.Group(name="snapshotfs", help="Create and mount filesystem snapshots.")
    registrations = [*_builtin_stores(), *registry.stores]
    seen: set[str] = set()
    for registration in registrations:
        if registration.name in seen or registration.name == "completion":
            raise RegistryError(
                f"duplicate or reserved store registration name {registration.name!r}"
            )
        seen.add(registration.name)
        root.add_command(registration.command_factory(registry), registration.name)
    root.add_command(_completion_command())
    return root


def _builtin_stores() -> tuple[StoreCLIRegistration, ...]:
    return (
        StoreCLIRegistration("sqlite", _sqlite_commands),
        StoreCLIRegistration("memory", _memory_commands),
    )


def _sqlite_commands(registry: CLIRegistry) -> click.Group:
    group = click.Group(name="sqlite", help="Create, mount, and display SQLite stores.")

    def create(**arguments: object) -> None:
        mountpoint = arguments["mount"]
        if mountpoint is None and arguments["simulate_missing_content"]:
            raise click.UsageError("--simulate-missing-content requires --mount")
        source, parser = _create_components(registry, arguments)
        store = api.create_sqlite_store(
            source,
            parser,
            str(arguments["output"]),
            overwrite=bool(arguments["overwrite"]),
        )
        if mountpoint is None:
            store.close()
            return
        with closing(store):
            api.mount_store(
                store,
                str(mountpoint),
                simulate_missing_content=bool(arguments["simulate_missing_content"]),
            )

    group.add_command(
        registry.component_command(
            name="create",
            help="Parse a source into a persistent SQLite store.",
            callback=create,
            parameters=[
                click.Argument(["output"], type=click.Path(path_type=str)),
                _source_option(registry),
                _parser_option(registry),
                click.Option(["--overwrite"], is_flag=True),
                click.Option(
                    ["--mount"],
                    type=click.Path(path_type=str),
                    help="Mount the new store immediately at this path.",
                ),
                _simulate_option(),
            ],
        )
    )

    @click.command(help="Mount an existing SQLite store read-only.")
    @click.argument("snapshot", type=click.Path(path_type=str))
    @click.argument("mountpoint", type=click.Path(path_type=str))
    @click.option(
        "--simulate-missing-content",
        is_flag=True,
        help="Return NUL stand-ins for declared missing file content.",
    )
    def mount(
        snapshot: str, mountpoint: str, simulate_missing_content: bool
    ) -> None:
        with api.open_sqlite_store(snapshot) as store:
            api.mount_store(
                store,
                mountpoint,
                simulate_missing_content=simulate_missing_content,
            )

    @click.command(help="Display an existing SQLite store.")
    @click.argument("snapshot", type=click.Path(path_type=str))
    @click.option("--json", "as_json", is_flag=True)
    def show(snapshot: str, as_json: bool) -> None:
        with api.open_sqlite_store(snapshot) as store:
            if as_json:
                click.echo(
                    json.dumps(json_document(store), indent=2, ensure_ascii=False)
                )
            else:
                print_tree(store)

    group.add_command(mount)
    group.add_command(show)
    return group


def _memory_commands(registry: CLIRegistry) -> click.Group:
    group = click.Group(name="memory", help="Build transient in-memory stores.")

    def mount(**arguments: object) -> None:
        source, parser = _create_components(registry, arguments)
        store = api.create_memory_store(source, parser)
        api.mount_store(
            store,
            str(arguments["mountpoint"]),
            simulate_missing_content=bool(arguments["simulate_missing_content"]),
        )

    group.add_command(
        registry.component_command(
            name="mount",
            help="Parse a source and mount it from memory.",
            callback=mount,
            parameters=[
                click.Argument(["mountpoint"], type=click.Path(path_type=str)),
                _source_option(registry),
                _parser_option(registry),
                _simulate_option(),
            ],
        )
    )
    return group


def _source_option(registry: CLIRegistry) -> click.Option:
    return click.Option(
        ["--source"],
        type=click.Choice(registry.source_names),
        required=True,
        help="Source implementation used to read the listing.",
    )


def _parser_option(registry: CLIRegistry) -> click.Option:
    return click.Option(
        ["--parser"],
        type=click.Choice(registry.parser_names),
        required=True,
        help="Parser implementation used to interpret the listing.",
    )


def _simulate_option() -> click.Option:
    return click.Option(
        ["--simulate-missing-content"],
        is_flag=True,
        help="Return NUL stand-ins for declared missing file content.",
    )


def _create_components(
    registry: CLIRegistry, arguments: Mapping[str, object]
) -> tuple[Source, Parser]:
    source_name = str(arguments["source"])
    parser_name = str(arguments["parser"])
    return (
        registry.create_source(source_name, arguments),
        registry.create_parser(parser_name, arguments),
    )


def _completion_command() -> click.Command:
    @click.command(name="completion", help="Print shell completion registration code.")
    @click.argument("shell", type=click.Choice(["bash", "zsh", "fish"]))
    @click.pass_context
    def completion(context: click.Context, shell: str) -> None:
        completion_class = get_completion_class(shell)
        if completion_class is None:
            raise click.ClickException(f"unsupported shell {shell!r}")
        complete = completion_class(
            cli=context.find_root().command,
            ctx_args={},
            prog_name="snapshotfs",
            complete_var="_SNAPSHOTFS_COMPLETE",
        )
        click.echo(complete.source())

    return completion


if __name__ == "__main__":
    raise SystemExit(main())
