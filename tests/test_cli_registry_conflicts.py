import click
import pytest

from snapshotfs.cli_registry import CLIRegistry, RegistryError, SourceRegistration


@pytest.mark.parametrize(
    "option", ["--simulate-missing-content", "--source", "--parser", "--help"]
)
def test_registration_cannot_reuse_command_option(option: str) -> None:
    registry = CLIRegistry(
        sources=[
            SourceRegistration(
                "conflicting",
                lambda _arguments: None,  # type: ignore[arg-type]
                (click.Option([option]),),
            )
        ]
    )
    with pytest.raises(RegistryError, match=r"argument conflict.*conflicting"):
        registry.selected_parameters(
            "conflicting",
            None,
            reserved_options=[
                "--simulate-missing-content",
                "--source",
                "--parser",
                "--help",
            ],
        )


@pytest.mark.parametrize(
    "destination", ["simulate_missing_content", "source", "parser", "mountpoint"]
)
def test_registration_cannot_reuse_command_destination(destination: str) -> None:
    registry = CLIRegistry(
        sources=[
            SourceRegistration(
                "conflicting",
                lambda _arguments: None,  # type: ignore[arg-type]
                (click.Option(["--component-value", destination]),),
            )
        ]
    )
    with pytest.raises(
        RegistryError,
        match=rf"duplicate destination '{destination}'",
    ):
        registry.selected_parameters(
            "conflicting",
            None,
            reserved_names=[
                "simulate_missing_content",
                "source",
                "parser",
                "mountpoint",
            ],
        )
