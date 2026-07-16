"""Shared clock conversion for stream and telemetry timestamps."""

from datetime import datetime, timedelta, timezone


BEIJING_TIME = timezone(timedelta(hours=8), name="UTC+8")
VALID_TIME_STANDARDS = {"local", "utc", "utc+8"}


def normalize_time_standard(value):
    normalized = str(value or "local").strip().lower().replace(" ", "")
    aliases = {
        "utc+08:00": "utc+8",
        "utc+08": "utc+8",
        "beijing": "utc+8",
        "beijingtime": "utc+8",
        "asia/shanghai": "utc+8",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in VALID_TIME_STANDARDS:
        valid = ", ".join(sorted(VALID_TIME_STANDARDS))
        raise ValueError(f"time_standard must be one of: {valid}")
    return normalized


def time_standard_label(value):
    standard = normalize_time_standard(value)
    return {"local": "LOCAL", "utc": "UTC", "utc+8": "UTC+8"}[standard]


def current_time(time_standard="local", clock=None):
    """Return an aware datetime converted to the requested time standard."""
    standard = normalize_time_standard(time_standard)
    target_timezone = {
        "local": None,
        "utc": timezone.utc,
        "utc+8": BEIJING_TIME,
    }[standard]

    if clock is None:
        if target_timezone is None:
            return datetime.now().astimezone()
        return datetime.now(target_timezone)

    value = clock()
    if value.tzinfo is None:
        if target_timezone is None:
            return value.astimezone()
        return value.replace(tzinfo=target_timezone)
    if target_timezone is None:
        return value.astimezone()
    return value.astimezone(target_timezone)
