from datetime import datetime, tzinfo
from typing import Optional


def is_aware(dt: datetime) -> bool:
    return dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None


def to_tz_unaware(dt: datetime, tz: Optional[tzinfo]) -> datetime:
    return dt.astimezone(tz).replace(tzinfo=None)
