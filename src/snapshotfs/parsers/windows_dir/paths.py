"""Windows path projection into SnapshotFS's mounted hierarchy."""

from pathlib import PureWindowsPath


def to_mounted_path(path: PureWindowsPath) -> tuple[str, ...]:
    return (path.drive[0].upper(), *path.parts[1:])
