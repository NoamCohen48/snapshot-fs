"""Structured diagnostics shared by parsers and importers."""

from dataclasses import dataclass
from enum import StrEnum

MAX_DIAGNOSTICS = 1_000


class Severity(StrEnum):
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ImportDiagnostic:
    severity: Severity
    code: str
    message: str
    line_number: int | None = None

    def __post_init__(self) -> None:
        if self.line_number is not None and (
            not isinstance(self.line_number, int)
            or isinstance(self.line_number, bool)
            or self.line_number <= 0
        ):
            raise ValueError(
                "diagnostic line number must be a positive integer or None"
            )
        values = (("diagnostic code", self.code), ("message", self.message))
        for description, value in values:
            try:
                value.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise ValueError(f"{description} is not valid Unicode") from exc


class DiagnosticCollector:
    """Count every diagnostic while retaining a bounded prefix."""

    def __init__(self, limit: int = MAX_DIAGNOSTICS) -> None:
        self._limit = limit
        self._items: list[ImportDiagnostic] = []
        self.total = 0
        self.has_errors = False

    @property
    def items(self) -> tuple[ImportDiagnostic, ...]:
        return tuple(self._items)

    def add(self, diagnostic: ImportDiagnostic) -> None:
        self.total += 1
        if diagnostic.severity is Severity.ERROR:
            self.has_errors = True
        if len(self._items) < self._limit:
            self._items.append(diagnostic)

    def error(self, code: str, message: str, line_number: int | None = None) -> None:
        self.add(ImportDiagnostic(Severity.ERROR, code, message, line_number))

    def warning(self, code: str, message: str, line_number: int | None = None) -> None:
        self.add(ImportDiagnostic(Severity.WARNING, code, message, line_number))
