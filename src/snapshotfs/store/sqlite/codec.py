"""Safe value codecs for SQLite artifacts."""

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any, cast

from snapshotfs.model.metadata import thaw_metadata


def encode_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def decode_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


def encode_metadata(metadata: Mapping[str, Any]) -> str:
    try:
        value = thaw_metadata(metadata)
        _validate_json(value)
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except RecursionError as exc:
        raise ValueError("metadata nesting is too deep") from exc


def decode_metadata(value: str) -> Mapping[str, Any]:
    if not isinstance(value, str):
        raise TypeError("metadata JSON must be text")
    try:
        decoded = json.loads(value)
    except RecursionError as exc:
        raise ValueError("metadata nesting is too deep") from exc
    if not isinstance(decoded, dict) or not all(
        isinstance(key, str) for key in decoded
    ):
        raise ValueError("metadata must be a JSON object with string keys")
    return cast(dict[str, Any], decoded)


def _validate_json(value: object) -> None:
    if value is None or isinstance(value, str | bool | int):
        return
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise ValueError("metadata contains a non-finite number")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json(item)
        return
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("metadata object keys must be strings")
        for item in value.values():
            _validate_json(item)
        return
    raise TypeError(f"unsupported metadata value {type(value).__name__}")
