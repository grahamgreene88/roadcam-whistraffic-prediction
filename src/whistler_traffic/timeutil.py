"""Time helpers. Everything is stored in UTC; Vancouver time is for display/features only."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

VANCOUVER = ZoneInfo("America/Vancouver")


def utc_now() -> datetime:
    return datetime.now(UTC)


def _require_aware(dt: datetime) -> None:
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"naive datetime not allowed: {dt!r}")


def to_vancouver(dt: datetime) -> datetime:
    _require_aware(dt)
    return dt.astimezone(VANCOUVER)


def key_timestamp(dt: datetime) -> str:
    """Compact, sortable UTC stamp for object keys, e.g. 20261125T230412Z."""
    _require_aware(dt)
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def iso_utc(dt: datetime) -> str:
    _require_aware(dt)
    return dt.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
