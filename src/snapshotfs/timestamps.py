"""Explicit source wall-clock interpretation, including daylight-saving gaps."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def source_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(
            f"unknown source timezone {name!r}; "
            "use an IANA name such as UTC or Europe/London"
        ) from exc


def localize(value: datetime, zone: ZoneInfo, ambiguous: str = "reject") -> datetime:
    candidates: dict[datetime, datetime] = {}
    for fold in (0, 1):
        candidate = value.replace(tzinfo=zone, fold=fold)
        instant = candidate.astimezone(UTC)
        if instant.astimezone(zone).replace(tzinfo=None) == value:
            candidates.setdefault(instant, candidate)
    if not candidates:
        raise ValueError(
            f"nonexistent local time {value.isoformat()} in {zone.key}; "
            "check the source timezone and listing"
        )
    ordered = sorted(candidates)
    if len(ordered) > 1 and ambiguous == "reject":
        raise ValueError(
            f"ambiguous local time {value.isoformat()} in {zone.key}; "
            "select --ambiguous-time earlier or later"
        )
    instant = ordered[-1] if ambiguous == "later" else ordered[0]
    return candidates[instant]
