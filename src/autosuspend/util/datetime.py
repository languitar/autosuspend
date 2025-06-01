from datetime import datetime, tzinfo


def is_aware(dt: datetime) -> bool:
    return dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None


def to_tz_unaware(dt: datetime, tz: tzinfo | None) -> datetime:
    """Convert a datetime to the given timezone and return a naive datetime (no tzinfo)."""
    dt = dt.replace(tzinfo=tz) if dt.tzinfo is None else dt.astimezone(tz)
    return dt.replace(tzinfo=None)
