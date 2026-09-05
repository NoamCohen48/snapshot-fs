"""Shared metadata typing and immutable defaults."""

from collections.abc import Mapping
from math import isfinite
from types import MappingProxyType
from typing import Any

type Metadata = Mapping[str, Any]
EMPTY_METADATA: Metadata = MappingProxyType({})


class FrozenList(tuple[Any, ...]):
    """Immutable representation of a JSON array."""


def freeze_metadata(metadata: Metadata) -> Metadata:
    return _freeze_mapping(metadata)


def thaw_metadata(metadata: Metadata) -> dict[str, Any]:
    return {key: _thaw_value(value) for key, value in metadata.items()}


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, FrozenList):
        return value
    if isinstance(value, list):
        return FrozenList(_freeze_value(item) for item in value)
    if isinstance(value, str):
        _require_unicode(value, "metadata string")
        return value
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("metadata contains a non-finite number")
        return value
    raise TypeError(f"unsupported metadata value {type(value).__name__}")


def _freeze_mapping(value: Mapping[Any, Any]) -> Metadata:
    result: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError("metadata object keys must be strings")
        _require_unicode(key, "metadata object key")
        result[key] = _freeze_value(item)
    return MappingProxyType(result)


def _require_unicode(value: str, description: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{description} is not valid Unicode") from exc


def _thaw_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_value(item) for key, item in value.items()}
    if isinstance(value, FrozenList):
        return [_thaw_value(item) for item in value]
    return value
