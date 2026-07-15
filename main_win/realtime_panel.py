"""实时巡检数据面板格式化工具。"""

import math
from numbers import Real


EMPTY_VALUE = "—"
FIELD_SOURCE_STATES = {
    "real",
    "virtual",
    "estimated",
    "mixed",
    "unavailable",
    "unknown",
}
SENSOR_SOURCE_FIELDS = (
    "gps",
    "robot_status",
    "velocity",
    "azimuth",
    "camera_height",
    "battery",
    "fault",
    "tree",
    "route",
)
ROBOT_STATUS_LABELS = {
    0: "待机/停止",
    1: "正常巡检",
    2: "到树作业",
    3: "充电",
    4: "暂停/人工",
    255: "故障",
}


def has_realtime_value(value):
    """判断值能否显示；数字 0 是有效数据。"""
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
    """只拼接真实存在的电池字段。"""
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


def format_tree_event(tree_event):
    """显示当前及左右果树编号，数值编号统一补足四位。"""
    tree_event = tree_event or {}
    id_fields = ("current_tree_id", "left_tree_id", "right_tree_id")
    if all(field in tree_event for field in id_fields):
        try:
            current, left, right = (
                int(tree_event[field]) for field in id_fields
            )
        except (TypeError, ValueError, OverflowError):
            return EMPTY_VALUE
        if min(current, left, right) < 0:
            return EMPTY_VALUE
        if current == left == right == 0:
            return "当前无树"
        current_text = f"{current:04d}" if current else "未确定"
        left_text = f"{left:04d}" if left else "无"
        right_text = f"{right:04d}" if right else "无"
        return f"当前 {current_text}\n左 {left_text} · 右 {right_text}"

    tree_code = tree_event.get("tree_code")
    return str(tree_code) if has_realtime_value(tree_code) else EMPTY_VALUE


def build_realtime_view(data):
    """将遥测快照转换为可显示文本和数据来源状态。"""
    data = data or {}
    status = data.get("status") or {}
    tree_event = data.get("tree_event") or {}
    channels = data.get("channels") or {}
    gps_data = data.get("gps") or {}
    declared_sources = data.get("field_sources") or {}

    mode = data.get("work_mode")
    active_channels = [name for name, enabled in channels.items() if enabled]
    data_mode_label = data.get("data_mode_label")
    work_mode_parts = [
        str(value) for value in (mode, data_mode_label) if has_realtime_value(value)
    ]
    robot_status = status.get("robot_status")
    route = status.get("route_index")
    waypoint = status.get("waypoint_index")
    route_parts = []
    if has_realtime_value(route):
        route_parts.append(f"路线 {int(route)}")
    if has_realtime_value(waypoint):
        route_parts.append(f"路径点 {int(waypoint)}")
    fault_code = status.get("fault_code")
    values = {
        "robot_status": (
            ROBOT_STATUS_LABELS.get(int(robot_status), f"状态 {int(robot_status)}")
            if has_realtime_value(robot_status)
            else EMPTY_VALUE
        ),
        "work_mode": " · ".join(work_mode_parts) if work_mode_parts else EMPTY_VALUE,
        "frame_index": (
            str(data["frame_index"])
            if has_realtime_value(data.get("frame_index"))
            else EMPTY_VALUE
        ),
        "disease_count": format_count(data.get("disease_count")),
        "tree": format_tree_event(tree_event),
        "velocity": format_number(status.get("velocity"), decimals=2, suffix=" m/s"),
        "azimuth": format_number(status.get("azimuth"), decimals=0, suffix="°"),
        "camera_height": format_number(
            status.get("eyepoint_height"), decimals=2, suffix=" m"
        ),
        "battery": format_battery(status.get("soc"), status.get("bat_voltage")),
        "route": " · ".join(route_parts) if route_parts else EMPTY_VALUE,
        "fault": (
            "无故障"
            if has_realtime_value(fault_code) and int(fault_code) == 0
            else f"0x{int(fault_code):04X}"
            if has_realtime_value(fault_code)
            else EMPTY_VALUE
        ),
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
        gps_field_source = "real"
    elif gps_available and (
        gps_source == "virtual" or gps_data.get("simulated") is True
    ):
        gps_field_source = "virtual"
    elif gps_available:
        gps_field_source = "unknown"
    else:
        gps_field_source = "unavailable"

    field_sources = {}
    for field, value in values.items():
        source = str(declared_sources.get(field) or "unknown").strip().lower()
        if value == EMPTY_VALUE:
            source = "unavailable"
        elif field == "gps":
            source = gps_field_source
        if source not in FIELD_SOURCE_STATES:
            source = "unknown"
        field_sources[field] = source

    active_sensor_sources = {
        field_sources[field]
        for field in SENSOR_SOURCE_FIELDS
        if values[field] != EMPTY_VALUE
    }
    has_real = bool(active_sensor_sources & {"real", "estimated"})
    has_virtual = "virtual" in active_sensor_sources
    if has_real and has_virtual:
        data_source = "mixed"
        data_source_label = "真实/虚拟混合"
    elif has_real:
        data_source = "real"
        data_source_label = "真实数据"
    elif has_virtual:
        data_source = "virtual"
        data_source_label = "虚拟数据"
    elif active_sensor_sources:
        data_source = "unknown"
        data_source_label = "来源未知"
    else:
        data_source = "waiting"
        data_source_label = "等待真实数据"

    return {
        "values": values,
        "field_sources": field_sources,
        "data_source": data_source,
        "data_source_label": data_source_label,
        "gps_available": gps_available,
    }
