"""Formatting helpers for the realtime patrol data panel."""

import math
from numbers import Real


EMPTY_VALUE = "—"
FIELD_SOURCE_STATES = {"real", "virtual", "estimated", "unavailable", "unknown"}


def has_realtime_value(value):
    """Return whether a value is suitable for display; numeric zero is valid."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Real):
        return math.isfinite(float(value))
    return True


def format_number(value, decimals=0, suffix=""):
    if not has_realtime_value(value):
        return EMPTY_VALUE
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return EMPTY_VALUE
    if not math.isfinite(number):
        return EMPTY_VALUE
    return f"{number:.{decimals}f}{suffix}"


def format_count(value, suffix=" 个"):
    if not has_realtime_value(value):
        return EMPTY_VALUE
    try:
        return f"{int(value)}{suffix}"
    except (TypeError, ValueError, OverflowError):
        return EMPTY_VALUE


def format_battery(soc, voltage):
    """Only include battery measurements that are actually available."""
    parts = []
    soc_text = format_number(soc, decimals=0, suffix="%")
    voltage_text = format_number(voltage, decimals=1, suffix=" V")
    if soc_text != EMPTY_VALUE:
        parts.append(soc_text)
    if voltage_text != EMPTY_VALUE:
        parts.append(voltage_text)
    return "  ·  ".join(parts) if parts else EMPTY_VALUE


def format_gps_dms(gps_dms):
    if not gps_dms or len(gps_dms) != 8:
        return EMPTY_VALUE
    if not all(has_realtime_value(value) for value in gps_dms):
        return EMPTY_VALUE
    lat_d, lat_m, lat_s, lat_dir, lon_d, lon_m, lon_s, lon_dir = gps_dms
    try:
        return (
            f"{int(lat_d)}°{int(lat_m):02d}'{float(lat_s):04.1f}\"{lat_dir}"
            f"\n{int(lon_d)}°{int(lon_m):02d}'{float(lon_s):04.1f}\"{lon_dir}"
        )
    except (TypeError, ValueError, OverflowError):
        return EMPTY_VALUE


def build_realtime_view(data):
    """Convert a telemetry payload into display-ready values and state labels."""
    data = data or {}
    status = data.get("status") or {}
    tree_event = data.get("tree_event") or {}
    channels = data.get("channels") or {}
    gps_data = data.get("gps") or {}
    declared_sources = data.get("field_sources") or {}

    mode = data.get("work_mode")
    active_channels = [name for name, enabled in channels.items() if enabled]
    values = {
        "work_mode": mode if has_realtime_value(mode) else EMPTY_VALUE,
        "frame_index": (
            str(data["frame_index"])
            if has_realtime_value(data.get("frame_index"))
            else EMPTY_VALUE
        ),
        "disease_count": format_count(data.get("disease_count")),
        "tree": (
            str(tree_event["tree_code"])
            if has_realtime_value(tree_event.get("tree_code"))
            else EMPTY_VALUE
        ),
        "velocity": format_number(status.get("velocity"), decimals=2, suffix=" m/s"),
        "azimuth": format_number(status.get("azimuth"), decimals=0, suffix="°"),
        "battery": format_battery(status.get("soc"), status.get("bat_voltage")),
        "gps": format_gps_dms(data.get("gps_dms")),
        "channels": "  ·  ".join(active_channels) if active_channels else "本地",
    }

    gps_available = values["gps"] != EMPTY_VALUE
    gps_source = str(gps_data.get("source") or "").strip().lower()
    if (
        gps_available
        and gps_source == "serial"
        and gps_data.get("valid") is True
        and gps_data.get("simulated") is not True
    ):
        data_source = "real"
        data_source_label = "真实数据"
    elif gps_available and (
        gps_source == "virtual" or gps_data.get("simulated") is True
    ):
        data_source = "virtual"
        data_source_label = "虚拟数据"
    elif gps_available:
        data_source = "unknown"
        data_source_label = "来源未知"
    else:
        data_source = "waiting"
        data_source_label = "等待真实数据"

    field_sources = {}
    for field, value in values.items():
        source = str(declared_sources.get(field) or "unknown").strip().lower()
        if value == EMPTY_VALUE:
            source = "unavailable"
        elif field == "gps":
            source = data_source if data_source in {"real", "virtual"} else source
        if source not in FIELD_SOURCE_STATES:
            source = "unknown"
        field_sources[field] = source

    return {
        "values": values,
        "field_sources": field_sources,
        "data_source": data_source,
        "data_source_label": data_source_label,
        "gps_available": gps_available,
    }
