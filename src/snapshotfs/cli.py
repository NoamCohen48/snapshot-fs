"""SnapshotFS command-line interface."""

import json
import os
import sys
from collections.abc import Mapping, Sequence
from contextlib import closing
from pathlib import Path

import click
from click.shell_completion import get_completion_class

from snapshotfs.cli_output import json_document, print_tree
from snapshotfs.cli_registry import (
    CLIRegistry,
    RegistryError,
    StoreCLIRegistration,
    default_registry,
)
from snapshotfs.doctor import doctor_command
from snapshotfs.fuse import FuseUnavailableError, mount_store
from snapshotfs.logging_setup import LoggingSession, logger, package_version
from snapshotfs.mount_session import WORKER_ENV, run_mounted, start_background, unmount
from snapshotfs.parser import Parser
from snapshotfs.source import Source, SourceError
from snapshotfs.store import ImportFailure
from snapshotfs.store.memory import create_memory_store
from snapshotfs.store.sqlite import create_sqlite_store, open_sqlite_store


def main(argv: Sequence[str] | None = None, registry: CLIRegistry | None = None) -> int:
    """Run the CLI and return its process exit status."""
    session = LoggingSession()
    session.arguments = list(argv) if argv is not None else sys.argv[1:]
    session.custom_registry = registry is not None
    try:
        status = _run(argv, registry, session)
        if status not in {0, 130} and session.path is not None:
            click.echo(f"Diagnostic log: {session.path}", err=True)
        return status
    finally:
        session.close()


def _run(
    argv: Sequence[str] | None, registry: CLIRegistry | None, session: LoggingSession
) -> int:
    try:
        command = build_cli(registry if registry is not None else default_registry())
        result = command.main(
            args=list(argv) if argv is not None else None,
            prog_name="snapshotfs",
            standalone_mode=False,
            obj=session,
        )
    except click.ClickException as exc:
        logger.debug("Command usage failed: %s", exc, exc_info=True)
        exc.show(file=sys.stderr)
        return exc.exit_code
    except ImportFailure as exc:
        logger.exception("Snapshot import failed")
        from snapshotfs.cli_output import format_diagnostic

        for diagnostic in exc.diagnostics:
            click.echo(format_diagnostic(diagnostic), err=True)
            logger.error(format_diagnostic(diagnostic))
        codes = {diagnostic.code for diagnostic in exc.diagnostics}
        hints = []
        if "DECODE_ERROR" in codes:
            hints.append(
                "Set --encoding to the producer's encoding "
                "(for example utf-8, cp1252, or utf-16)."
            )
        if "INVALID_LOCAL_TIME" in codes:
            hints.append(
                "Check --source-timezone. Repeated DST times require "
                "--ambiguous-time earlier or later; nonexistent times are rejected."
            )
        if codes & {"INVALID_DATETIME", "INVALID_TIME", "MALFORMED_ENTRY"}:
            hints.append(
                "Check --date-format mdy, dmy, or ymd against the source dates; "
                "expected entries contain a date, time, <DIR> or size, and name."
            )
        if codes & {"UNKNOWN_LINE", "MISSING_SECTION"}:
            hints.append(
                "windows-dir requires English Windows dir /s output, including "
                "'Directory of' headers; localized output and UNC paths "
                "are unsupported."
            )
        if any(
            "SUMMARY" in code or "FOOTER" in code or "TOTAL_MISMATCH" in code
            for code in codes
        ):
            hints.append(
                "Keep the complete dir /s listing, including File(s), Dir(s), "
                "and Total Files Listed summaries; "
                "do not trim or concatenate listings."
            )
        for hint in hints:
            click.echo(f"hint: {hint}", err=True)
            logger.info("Import hint: %s", hint)
        if exc.diagnostic_count > len(exc.diagnostics):
            click.echo(
                f"{exc.diagnostic_count} diagnostics observed; "
                f"showing first {len(exc.diagnostics)}",
                err=True,
            )
        return 1
    except SourceError as exc:
        logger.exception("Source access failed")
        click.echo(f"error: {exc}", err=True)
        return 1
    except FuseUnavailableError as exc:
        logger.exception("FUSE setup failed")
        click.echo(f"error: {exc}", err=True)
        return 1
    except click.Abort:
        logger.info("Interrupted by user")
        click.echo("Aborted!", err=True)
        return 130
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 130
    except (OSError, RuntimeError, RegistryError) as exc:
        logger.exception("Command failed")
        click.echo(f"error: {exc}", err=True)
        return 1
    except Exception as exc:
        logger.exception("Unexpected command failure")
        click.echo(f"error: {exc}; see the log file or retry with --verbose", err=True)
        return 1
    logger.info("Command completed")
    return result if isinstance(result, int) else 0


def build_cli(registry: CLIRegistry) -> click.Group:
    """Build a root command from built-in and registered store command groups."""

    @click.group(name="snapshotfs", help="Create and mount filesystem snapshots.")
    @click.version_option(version=package_version(), prog_name="snapshotfs")
    @click.option(
        "--verbose",
        "-v",
        is_flag=True,
        help="Show diagnostic logs and tracebacks on stderr.",
    )
    @click.option(
        "--log-file",
        type=click.Path(dir_okay=False),
        help="Override the rotating diagnostic log file.",
    )
    @click.pass_context
    def root(context: click.Context, verbose: bool, log_file: str | None) -> None:
        session = context.obj
        if not isinstance(session, LoggingSession):
            session = LoggingSession()
            context.call_on_close(session.close)
            context.obj = session
        session.configure(verbose and os.environ.get(WORKER_ENV) != "1", log_file)
        logger.debug("Command: %s", context.invoked_subcommand)

    registrations = [*_builtin_stores(), *registry.stores]
    seen: set[str] = set()
    for registration in registrations:
        if registration.name in seen or registration.name in {
            "completion",
            "doctor",
            "run",
            "unmount",
        }:
            raise RegistryError(
                f"duplicate or reserved store registration name {registration.name!r}"
            )
        seen.add(registration.name)
        root.add_command(registration.command_factory(registry), registration.name)
    root.add_command(_completion_command())
    root.add_command(doctor_command())
    root.add_command(_unmount_command())
    root.add_command(_run_command())
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
        if arguments["background"] and mountpoint is None:
            raise click.UsageError("--background requires --mount")
        if mountpoint is not None and _background_requested(arguments, str(mountpoint)):
            return
        source, parser = _create_components(registry, arguments)
        logger.info(
            "Creating SQLite snapshot %s (overwrite=%s)",
            arguments["output"],
            arguments["overwrite"],
        )
        store = create_sqlite_store(
            source,
            parser,
            str(arguments["output"]),
            overwrite=bool(arguments["overwrite"]),
        )
        if mountpoint is None:
            store.close()
            return
        with closing(store):
            mount_store(
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
                *_mount_mode_options(),
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
    @click.option(
        "--background/--foreground",
        default=False,
        help="Detach after readiness; foreground is the default.",
    )
    @click.option(
        "--startup-timeout",
        type=click.FloatRange(min=0, min_open=True),
        default=120.0,
        show_default=True,
    )
    def mount(
        snapshot: str,
        mountpoint: str,
        simulate_missing_content: bool,
        background: bool,
        startup_timeout: float,
    ) -> None:
        if _background_requested(
            {"background": background, "startup_timeout": startup_timeout}, mountpoint
        ):
            return
        logger.info(
            "Opening SQLite snapshot %s for mounting at %s", snapshot, mountpoint
        )
        with open_sqlite_store(snapshot) as store:
            mount_store(
                store,
                mountpoint,
                simulate_missing_content=simulate_missing_content,
            )

    @click.command(help="Display an existing SQLite store.")
    @click.argument("snapshot", type=click.Path(path_type=str))
    @click.option("--json", "as_json", is_flag=True)
    def show(snapshot: str, as_json: bool) -> None:
        logger.info("Inspecting SQLite snapshot %s", snapshot)
        with open_sqlite_store(snapshot) as store:
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
        if _background_requested(arguments, str(arguments["mountpoint"])):
            return
        source, parser = _create_components(registry, arguments)
        store = create_memory_store(source, parser)
        mount_store(
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
                *_mount_mode_options(),
            ],
        )
    )
    return group


def _mount_mode_options() -> list[click.Option]:
    return [
        click.Option(
            ["--background/--foreground"],
            default=False,
            help="Detach after readiness; foreground is the default.",
        ),
        click.Option(
            ["--startup-timeout"],
            type=click.FloatRange(min=0, min_open=True),
            default=120.0,
            show_default=True,
        ),
    ]


def _background_requested(arguments: Mapping[str, object], mountpoint: str) -> bool:
    if not arguments["background"] or os.environ.get(WORKER_ENV) == "1":
        return False
    session = click.get_current_context().find_root().obj
    if (
        not isinstance(session, LoggingSession)
        or session.custom_registry
        or not session.arguments
    ):
        raise click.UsageError("background mode requires the default CLI registry")
    start_background(
        session.arguments, Path(mountpoint), float(str(arguments["startup_timeout"]))
    )
    click.echo(f"Mounted {Path(mountpoint).resolve()} in background")
    return True


def _unmount_command() -> click.Command:
    @click.command(name="unmount", help="Unmount a SnapshotFS filesystem and return.")
    @click.argument("mountpoint", type=click.Path(path_type=Path))
    def command(mountpoint: Path) -> None:
        unmount(mountpoint)

    return command


def _run_command() -> click.Command:
    @click.command(
        name="run", help="Mount a snapshot temporarily, run COMMAND, then unmount."
    )
    @click.argument("snapshot", type=click.Path(path_type=str))
    @click.argument("command", nargs=-1, type=click.UNPROCESSED, required=True)
    @click.option("--simulate-missing-content", is_flag=True)
    @click.option(
        "--startup-timeout",
        type=click.FloatRange(min=0, min_open=True),
        default=120.0,
        show_default=True,
    )
    def run(
        snapshot: str,
        command: tuple[str, ...],
        simulate_missing_content: bool,
        startup_timeout: float,
    ) -> int:
        session = click.get_current_context().find_root().obj
        options = (
            ["--log-file", str(session.path)]
            if isinstance(session, LoggingSession) and session.path
            else []
        )
        return run_mounted(
            snapshot,
            command,
            options,
            simulate=simulate_missing_content,
            timeout=startup_timeout,
        )

    return run


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
    logger.info("Selecting source=%s parser=%s", source_name, parser_name)
    logger.debug("Component settings: %r", dict(arguments))
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
