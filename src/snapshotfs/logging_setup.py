"""CLI-owned logging; importing the SDK never configures application logging."""

import logging
import os
import platform
from importlib.metadata import PackageNotFoundError, version
from logging.handlers import RotatingFileHandler
from pathlib import Path

import click

logger = logging.getLogger("snapshotfs")
logger.addHandler(logging.NullHandler())


def package_version() -> str:
    try:
        return version("snapshotfs")
    except PackageNotFoundError:
        return "unknown"


def default_log_path() -> Path:
    if platform.system() == "Linux":
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    else:
        base = Path(click.get_app_dir("snapshotfs"))
    return (
        base / "snapshotfs" / "snapshotfs.log"
        if platform.system() == "Linux"
        else base / "snapshotfs.log"
    )


class LoggingSession:
    def __init__(self) -> None:
        self.handlers: list[logging.Handler] = []
        self.path: Path | None = None
        self.arguments: list[str] = []
        self.custom_registry = False
        self.previous_level = logger.level
        self.previous_propagate = logger.propagate
        self.dependencies = [logging.getLogger(name) for name in ("pyfuse3", "trio")]
        self.dependency_settings = [
            (item.level, item.propagate) for item in self.dependencies
        ]

    def configure(self, verbose: bool, log_file: str | None) -> None:
        path = Path(log_file).expanduser() if log_file else default_log_path()
        try:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            os.close(descriptor)
            handler = RotatingFileHandler(
                path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
            )
        except OSError as exc:
            if log_file:
                raise click.ClickException(
                    f"cannot open log file {path}: {exc}"
                ) from exc
            click.echo(f"warning: cannot open default log file {path}: {exc}", err=True)
        else:
            handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
            )
            self.handlers.append(handler)
            self.path = path
        if verbose:
            console = logging.StreamHandler()
            console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
            self.handlers.append(console)
        if not self.handlers:
            self.handlers.append(logging.NullHandler())
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        for configured_handler in self.handlers:
            logger.addHandler(configured_handler)
        for dependency in self.dependencies:
            dependency.setLevel(logging.DEBUG)
            dependency.propagate = False
            for configured_handler in self.handlers:
                dependency.addHandler(configured_handler)
        logger.info(
            "SnapshotFS %s; platform=%s; Python=%s",
            package_version(),
            platform.platform(),
            platform.python_version(),
        )
        logger.debug("Log file: %s", path)

    def close(self) -> None:
        for dependency, (level, propagate) in zip(
            self.dependencies, self.dependency_settings, strict=True
        ):
            for configured_handler in self.handlers:
                dependency.removeHandler(configured_handler)
            dependency.setLevel(level)
            dependency.propagate = propagate
        for handler in self.handlers:
            logger.removeHandler(handler)
            handler.close()
        self.handlers.clear()
        logger.setLevel(self.previous_level)
        logger.propagate = self.previous_propagate
