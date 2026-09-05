from contextlib import AbstractContextManager
from typing import BinaryIO, Protocol


class Source(Protocol):
    @property
    def uri(self) -> str: ...

    @property
    def size(self) -> int | None: ...

    def open(self) -> AbstractContextManager[BinaryIO]: ...
