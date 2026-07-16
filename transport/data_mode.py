"""真实、调试和仿真三种数据来源策略。"""

from dataclasses import dataclass
from typing import Optional, Tuple


REAL_MODE = "real"
DEBUG_MODE = "debug"
SIMULATION_MODE = "simulation"
DATA_MODES = (REAL_MODE, DEBUG_MODE, SIMULATION_MODE)
DEFAULT_DATA_MODE = DEBUG_MODE

GpsDms = Tuple[int, int, float, str, int, int, float, str]

STATUS_FIELDS = (
    "robot_status",
    "velocity",
    "azimuth",
    "bat_voltage",
    "soc",
    "route_index",
    "waypoint_index",
    "eyepoint_height",
    "fault_code",
)

UDP_STATUS_FIELDS = (
    "robot_status",
    "velocity",
    "azimuth",
    "bat_voltage",
    "soc",
    "eyepoint_height",
)


@dataclass(frozen=True)
class DataModePolicy:
    name: str
    label: str
    use_real_telemetry: bool
    use_serial_gps: bool
    use_virtual_gps: bool
    use_virtual_status: bool
    use_virtual_events: bool
    force_virtual: bool


POLICIES = {
    REAL_MODE: DataModePolicy(
        name=REAL_MODE,
        label="真实",
        use_real_telemetry=True,
        use_serial_gps=True,
        use_virtual_gps=False,
        use_virtual_status=False,
        use_virtual_events=False,
        force_virtual=False,
    ),
    DEBUG_MODE: DataModePolicy(
        name=DEBUG_MODE,
        label="调试",
        use_real_telemetry=True,
        use_serial_gps=True,
        use_virtual_gps=True,
        use_virtual_status=True,
        use_virtual_events=True,
        force_virtual=False,
    ),
    SIMULATION_MODE: DataModePolicy(
        name=SIMULATION_MODE,
        label="仿真",
        use_real_telemetry=False,
        use_serial_gps=False,
        use_virtual_gps=True,
        use_virtual_status=True,
        use_virtual_events=True,
        force_virtual=True,
    ),
}


def normalize_data_mode(value: Optional[str]) -> str:
    mode = str(value or DEFAULT_DATA_MODE).strip().lower()
    if mode not in POLICIES:
        choices = ", ".join(DATA_MODES)
        raise ValueError(f"未知数据模式 {value!r}，可选值：{choices}")
    return mode


def get_data_mode_policy(value: Optional[str]) -> DataModePolicy:
    return POLICIES[normalize_data_mode(value)]


def empty_status_data() -> dict:
    """显式返回缺失值，真实模式不得自动伪造遥测。"""
    return {field: None for field in STATUS_FIELDS}


def select_gps_dms(
    policy: DataModePolicy,
    gps_snapshot=None,
    virtual_gps_dms: Optional[GpsDms] = None,
) -> Optional[GpsDms]:
    if (
        not policy.force_virtual
        and gps_snapshot is not None
        and getattr(gps_snapshot, "valid", False)
    ):
        real_gps_dms = gps_snapshot.to_dms()
        if real_gps_dms is not None:
            return real_gps_dms
    if policy.use_virtual_gps:
        return virtual_gps_dms
    return None


def merge_status_data(
    policy: DataModePolicy,
    real_status_data: Optional[dict] = None,
    virtual_status_data: Optional[dict] = None,
) -> dict:
    """逐字段合并：真实优先、调试可回退、仿真只用虚拟值。"""
    real_status = real_status_data or {}
    virtual_status = virtual_status_data or {}
    merged = empty_status_data()
    for field in STATUS_FIELDS:
        real_value = real_status.get(field)
        virtual_value = virtual_status.get(field)
        if policy.force_virtual:
            merged[field] = virtual_value
        elif real_value is not None:
            merged[field] = real_value
        elif policy.use_virtual_status:
            merged[field] = virtual_value
    return merged


def missing_udp_telemetry_fields(status_data: dict, gps_dms) -> list:
    missing = [
        field for field in UDP_STATUS_FIELDS
        if status_data.get(field) is None
    ]
    if gps_dms is None or len(gps_dms) != 8 or any(value is None for value in gps_dms):
        missing.append("gps")
    return missing


def map_common_status_to_udp(robot_status, tree_present: bool = False) -> int:
    """把电控通用状态转换为甲方 B 旧 UDP 状态码。"""
    if tree_present:
        return 1
    return {
        0: 0,
        1: 0,
        2: 1,
        3: 2,
        4: 0,
        255: 255,
    }.get(int(robot_status), 0)
