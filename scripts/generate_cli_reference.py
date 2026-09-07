"""Generate the committed CLI help reference with contextual parameters."""

from __future__ import annotations

import sys
from pathlib import Path

from click.testing import CliRunner

from snapshotfs.cli import build_cli
from snapshotfs.cli_registry import default_registry

OUTPUT = Path(__file__).parents[1] / "docs" / "reference" / "cli.md"
CASES = (
    ("Root Command", ("--help",)),
    ("SQLite Commands", ("sqlite", "--help")),
    (
        "SQLite Create",
        (
            "sqlite",
            "create",
            "--source",
            "file",
            "--parser",
            "windows-dir",
            "--help",
        ),
    ),
    ("SQLite Mount", ("sqlite", "mount", "--help")),
    ("SQLite Show", ("sqlite", "show", "--help")),
    ("Memory Commands", ("memory", "--help")),
    (
        "Memory Mount",
        (
            "memory",
            "mount",
            "--source",
            "file",
            "--parser",
            "windows-dir",
            "--help",
        ),
    ),
    ("Completion", ("completion", "--help")),
)


def render() -> str:
    sections = [
        "# CLI Reference",
        "",
        "[Documentation](../index.md)",
        "",
        "This file is generated from the built-in Click command tree. The",
        "create and memory-mount help is rendered with the built-in source and parser",
        "selected so their contextual parameters are included.",
        "",
        "Regenerate it with `uv run python scripts/generate_cli_reference.py`.",
        "",
    ]
    runner = CliRunner()
    for title, arguments in CASES:
        result = runner.invoke(
            build_cli(default_registry()),
            list(arguments),
            color=False,
            terminal_width=88,
        )
        if result.exit_code != 0:
            raise RuntimeError(
                f"help generation failed for {title}: {result.output}"
            ) from result.exception
        command = "snapshotfs " + " ".join(arguments)
        sections.extend(
            [
                f"## {title}",
                "",
                f"`{command}`",
                "",
                "```text",
                result.output.rstrip(),
                "```",
                "",
            ]
        )
    return "\n".join(sections)


def main() -> int:
    content = render()
    if sys.argv[1:] == ["--check"]:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != content:
            print(
                f"{OUTPUT} is stale; run scripts/generate_cli_reference.py",
                file=sys.stderr,
            )
            return 1
        return 0
    if sys.argv[1:]:
        print("usage: generate_cli_reference.py [--check]", file=sys.stderr)
        return 2
    OUTPUT.write_text(content, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
