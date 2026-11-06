"""Read-only FUSE readiness checks; does not attempt to mount or modify the host."""

import importlib
import os
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path

import click

from snapshotfs.logging_setup import (
    LoggingSession,
    default_log_path,
    logger,
    package_version,
)


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def check_environment(mountpoint: Path | None = None) -> list[Check]:
    checks = [
        Check(
            "platform",
            platform.system() == "Linux",
            f"{platform.system()}; FUSE mounting requires Linux",
        )
    ]
    for module in ("pyfuse3", "trio"):
        try:
            importlib.import_module(module)
        except (ImportError, OSError) as exc:
            checks.append(
                Check(
                    module,
                    False,
                    f"{exc}; install the Linux package or "
                    "snapshotfs[fuse] and system fuse3",
                )
            )
        else:
            checks.append(Check(module, True, "available"))
    helper = shutil.which("fusermount3")
    checks.append(
        Check(
            "fusermount3",
            helper is not None,
            helper or "install the system fuse3 package",
        )
    )
    device = Path("/dev/fuse")
    checks.append(
        Check(
            "FUSE device",
            device.exists(),
            "/dev/fuse"
            if device.exists()
            else "enable the host FUSE module (sudo modprobe fuse); "
            "expose /dev/fuse to containers",
        )
    )
    checks.append(
        Check(
            "device access",
            device.exists() and os.access(device, os.R_OK | os.W_OK),
            "read/write access to /dev/fuse required; "
            "check device permissions and container policy",
        )
    )
    if mountpoint is not None:
        try:
            if not mountpoint.is_dir():
                detail = "create a directory owned by your user"
                ok = False
            elif os.path.ismount(mountpoint):
                detail, ok = "already mounted; unmount it first", False
            elif any(mountpoint.iterdir()):
                detail, ok = "choose an empty directory", False
            else:
                ok = os.access(mountpoint, os.W_OK | os.X_OK)
                detail = "empty directory; write/search access required"
        except OSError as exc:
            detail, ok = str(exc), False
        checks.append(Check("mountpoint", ok, f"{mountpoint}: {detail}"))
    return checks


def doctor_command() -> click.Command:
    @click.command(
        name="doctor",
        help="Check Linux FUSE setup without mounting or changing the host.",
    )
    @click.option(
        "--mountpoint",
        type=click.Path(path_type=Path),
        help="Also check this proposed mount directory.",
    )
    def doctor(mountpoint: Path | None) -> int:
        click.echo(
            f"SnapshotFS {package_version()} | {platform.system()} | "
            f"Python {platform.python_version()}"
        )
        checks = check_environment(mountpoint)
        for check in checks:
            message = f"{'OK' if check.ok else 'FAIL'} {check.name}: {check.detail}"
            click.echo(message)
            logger.info(message)
        session = click.get_current_context().find_root().obj
        if isinstance(session, LoggingSession) and session.path is not None:
            click.echo(f"Diagnostic log: {session.path}")
        else:
            click.echo(f"Default log: {default_log_path()} (override with --log-file)")
        click.echo(
            "Checks do not prove kernel/container mount permission; "
            "an actual mount is the final check."
        )
        return 0 if all(check.ok for check in checks) else 1

    return doctor
