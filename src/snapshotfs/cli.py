# PYTHON_ARGCOMPLETE_OK
"""SnapshotFS command-line inspection interface."""

import argparse
import json
import os
import shlex
import sys
from collections.abc import Sequence

import argcomplete
from argcomplete.shell_integration import shellcode

import snapshotfs.api as api
from snapshotfs.cli_output import format_diagnostic, json_document, print_tree
from snapshotfs.cli_registry import CLIRegistry, default_registry
from snapshotfs.import_service import ImportFailure
from snapshotfs.sources import SourceError


def main(argv: Sequence[str] | None = None, registry: CLIRegistry | None = None) -> int:
    active_registry = registry if registry is not None else default_registry()
    execution_argv = list(argv) if argv is not None else sys.argv[1:]
    completion_argv = _completion_arguments(active_registry)
    selector = _build_selector_parser(active_registry, required=completion_argv is None)
    selector_args, _ = selector.parse_known_args(
        execution_argv if completion_argv is None else completion_argv
    )
    source_name = getattr(selector_args, "source", None)
    parser_name = getattr(selector_args, "parser", None)
    parser = _build_parser(active_registry, source_name, parser_name)
    argcomplete.autocomplete(parser)
    args = parser.parse_args(argv)

    if args.command == "completion":
        print(shellcode(["snapshotfs"], shell=args.shell))
        return 0

    try:
        if args.command == "inspect":
            source = active_registry.create_source(args.source, args)
            listing_parser = active_registry.create_parser(args.parser, args)
            memory_store = api.create_memory_store(source, listing_parser)
            if args.as_json:
                print(
                    json.dumps(
                        json_document(memory_store), indent=2, ensure_ascii=False
                    )
                )
            else:
                print_tree(memory_store)
        elif args.command == "mount":
            source = active_registry.create_source(args.source, args)
            listing_parser = active_registry.create_parser(args.parser, args)
            memory_store = api.create_memory_store(source, listing_parser)
            api.mount_store(
                memory_store,
                args.mountpoint,
                simulate_missing_content=args.simulate_missing_content,
            )
        elif args.command == "import":
            source = active_registry.create_source(args.source, args)
            listing_parser = active_registry.create_parser(args.parser, args)
            sqlite_store = api.create_sqlite_store(
                source, listing_parser, args.output, overwrite=args.overwrite
            )
            sqlite_store.close()
        elif args.command == "inspect-store":
            with api.open_sqlite_store(args.snapshot) as sqlite_store:
                if args.as_json:
                    print(
                        json.dumps(
                            json_document(sqlite_store), indent=2, ensure_ascii=False
                        )
                    )
                else:
                    print_tree(sqlite_store)
        else:
            with api.open_sqlite_store(args.snapshot) as sqlite_store:
                api.mount_store(
                    sqlite_store,
                    args.mountpoint,
                    simulate_missing_content=args.simulate_missing_content,
                )
    except ImportFailure as exc:
        for diagnostic in exc.diagnostics:
            print(format_diagnostic(diagnostic), file=sys.stderr)
        if exc.diagnostic_count > len(exc.diagnostics):
            print(
                f"{exc.diagnostic_count} diagnostics observed; "
                f"showing first {len(exc.diagnostics)}",
                file=sys.stderr,
            )
        return 1
    except SourceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except api.FuseUnavailableError:
        print(
            "error: FUSE support is unavailable; install it with "
            "`uv sync --extra fuse`",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        pass
    except (OSError, RuntimeError) as exc:
        if args.command in {"mount", "mount-store"}:
            message = f"cannot mount {args.mountpoint}: {exc}"
        else:
            message = str(exc)
        print(f"error: {message}", file=sys.stderr)
        return 1
    return 0


def _build_parser(
    registry: CLIRegistry | None = None,
    source_name: str | None = None,
    parser_name: str | None = None,
) -> argparse.ArgumentParser:
    active_registry = registry if registry is not None else default_registry()
    parser = argparse.ArgumentParser(prog="snapshotfs")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="validate and print a listing")
    inspect.add_argument("--json", action="store_true", dest="as_json")
    _add_component_options(inspect, active_registry, source_name, parser_name)
    mount = commands.add_parser("mount", help="mount a listing read-only")
    mount.add_argument(
        "--simulate-missing-content",
        action="store_true",
        help="return NUL stand-ins for declared missing file content",
    )
    _add_component_options(
        mount,
        active_registry,
        source_name,
        parser_name,
        reserved_destinations={"mountpoint"},
    )
    mount.add_argument("mountpoint")
    import_command = commands.add_parser(
        "import", help="create a persistent SQLite snapshot artifact"
    )
    import_command.add_argument("output")
    import_command.add_argument("--overwrite", action="store_true")
    _add_component_options(
        import_command,
        active_registry,
        source_name,
        parser_name,
        reserved_destinations={"output", "overwrite"},
    )
    inspect_store = commands.add_parser(
        "inspect-store", help="inspect a persistent SQLite snapshot"
    )
    inspect_store.add_argument("snapshot")
    inspect_store.add_argument("--json", action="store_true", dest="as_json")
    mount_store = commands.add_parser(
        "mount-store", help="mount a persistent SQLite snapshot read-only"
    )
    mount_store.add_argument("snapshot")
    mount_store.add_argument("mountpoint")
    mount_store.add_argument(
        "--simulate-missing-content",
        action="store_true",
        help="return NUL stand-ins for declared missing file content",
    )
    completion = commands.add_parser(
        "completion", help="print shell completion registration code"
    )
    completion.add_argument("shell", choices=["bash", "zsh"])
    return parser


def _add_component_options(
    command: argparse.ArgumentParser,
    registry: CLIRegistry,
    source_name: str | None,
    parser_name: str | None,
    *,
    reserved_destinations: set[str] | None = None,
) -> None:
    command.add_argument("--source", choices=registry.source_names, required=True)
    command.add_argument("--parser", choices=registry.parser_names, required=True)
    registry.add_selected_arguments(
        command,
        source_name,
        parser_name,
        reserved_destinations={"command", *(reserved_destinations or set())},
    )


def _build_selector_parser(
    registry: CLIRegistry, *, required: bool
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="snapshotfs", add_help=False)
    commands = parser.add_subparsers(dest="command", required=required)
    for name in ("inspect", "mount", "import"):
        command = commands.add_parser(name, add_help=False)
        command.add_argument(
            "--source", choices=registry.source_names, required=required
        )
        command.add_argument(
            "--parser", choices=registry.parser_names, required=required
        )
    for name in ("inspect-store", "mount-store", "completion"):
        commands.add_parser(name, add_help=False)
    return parser


def _completion_arguments(registry: CLIRegistry) -> list[str] | None:
    if "_ARGCOMPLETE" not in os.environ:
        return None
    line = os.environ.get("COMP_LINE", "")
    try:
        point = int(os.environ.get("COMP_POINT", len(line)))
    except ValueError:
        point = len(line)
    tokens: list[str] = []
    lexer = shlex.shlex(line[: max(0, point)], posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        for token in lexer:
            tokens.append(token)
    except ValueError:
        pass
    return _selector_arguments(tokens[1:], registry) if tokens else []


def _selector_arguments(arguments: Sequence[str], registry: CLIRegistry) -> list[str]:
    commands = {
        "inspect",
        "mount",
        "import",
        "inspect-store",
        "mount-store",
        "completion",
    }
    if not arguments or arguments[0] not in commands:
        return []
    selected = [arguments[0]]
    index = 1
    while index < len(arguments):
        argument = arguments[index]
        if argument in {"--source", "--parser"}:
            if index + 1 < len(arguments) and not arguments[index + 1].startswith("-"):
                value = arguments[index + 1]
                names = (
                    registry.source_names
                    if argument == "--source"
                    else registry.parser_names
                )
                if value in names:
                    selected.extend((argument, value))
                index += 1
        elif (
            argument.startswith("--source=")
            and argument.removeprefix("--source=") in registry.source_names
        ) or (
            argument.startswith("--parser=")
            and argument.removeprefix("--parser=") in registry.parser_names
        ):
            selected.append(argument)
        index += 1
    return selected


if __name__ == "__main__":
    raise SystemExit(main())
