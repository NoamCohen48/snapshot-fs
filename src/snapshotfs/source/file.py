"""Local binary file source."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO


class SourceError(OSError):
    """A source could not be inspected or opened."""


class FileSource:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    @property
    def uri(self) -> str:
        return self.path.absolute().as_uri()

    @property
    def size(self) -> int | None:
        try:
            return self.path.stat().st_size
        except OSError as exc:
            message = f"cannot inspect source {self.path!s}: {exc.strerror}"
            raise SourceError(message) from exc

    @contextmanager
    def open(self) -> Iterator[BinaryIO]:
        try:
            stream = self.path.open("rb")
        except OSError as exc:
            message = f"cannot open source {self.path!s}: {exc.strerror}"
            raise SourceError(message) from exc
        try:
            yield stream
        finally:
            stream.close()
