"""电控端 58 字节统一遥测协议定义。"""

from dataclasses import asdict, dataclass
import math
import struct
import time
from typing import List, Optional, Tuple


FRAME_HEAD = b"\xAA\x55"
FRAME_TAIL = b"\x0D\x0A"
PROTOCOL_VERSION = 0x01
MESSAGE_TYPE_TELEMETRY = 0x01
PAYLOAD_SIZE = 46
FRAME_SIZE = 58

FLAG_GPS = 0x0001
FLAG_ROUTE = 0x0002
FLAG_TREE = 0x0004
FLAG_AZIMUTH = 0x0008
FLAG_VELOCITY = 0x0010
FLAG_CAMERA_HEIGHT = 0x0020
FLAG_BATTERY_VOLTAGE = 0x0040
FLAG_SOC = 0x0080
FLAG_TIMESTAMP = 0x0100
FLAG_FAULT = 0x0200
DEFINED_FLAGS_MASK = 0x03FF

VALID_ROBOT_STATUSES = {0, 1, 2, 3, 4, 255}
VALID_GPS_FIXES = {0, 1, 2, 4, 5}
VALID_POSITION_FIXES = {1, 2, 4, 5}

PAYLOAD_STRUCT = struct.Struct(">BBHHHHHHBBBHiiiIHHHHBH")
HEADER_STRUCT = struct.Struct(">BBHH")


class TelemetryProtocolError(ValueError):
    """遥测报文格式或字段错误。"""


class TelemetryChecksumError(TelemetryProtocolError):
    """遥测报文 CRC16 校验失败。"""


@dataclass(frozen=True)
class RobotTelemetry:
    """一包已经通过协议校验的电控遥测数据。"""

    sequence: int
    robot_id: int
    robot_status: int
    valid_flags: int
    route_id: int
    waypoint_id: int
    current_tree_id: int
    left_tree_id: int
    right_tree_id: int
    camera_side: int
    gps_fix: int
    satellites: int
    hdop_x100: int
    longitude_e7: int
    latitude_e7: int
    altitude_cm: int
    timestamp: int
    azimuth_x100: int
    velocity_mm_s: int
    camera_height_mm: int
    battery_mv: int
    soc: int
    fault_code: int
    received_at_ms: int

    def has(self, flag: int) -> bool:
        return bool(self.valid_flags & flag)

    @property
    def gps_valid(self) -> bool:
        return self.has(FLAG_GPS) and self.gps_fix in VALID_POSITION_FIXES

    @property
    def longitude(self) -> Optional[float]:
        return self.longitude_e7 / 10_000_000.0 if self.gps_valid else None

    @property
    def latitude(self) -> Optional[float]:
        return self.latitude_e7 / 10_000_000.0 if self.gps_valid else None

    @property
    def altitude_m(self) -> Optional[float]:
        return self.altitude_cm / 100.0 if self.gps_valid else None

    @property
    def actual_velocity_mps(self) -> Optional[float]:
        return self.velocity_mm_s / 1000.0 if self.has(FLAG_VELOCITY) else None

    def to_dms(self) -> Optional[Tuple[int, int, float, str, int, int, float, str]]:
        """将有效十进制度坐标转换为平台使用的度分秒。"""
        if not self.gps_valid:
            return None
        lat_d, lat_m, lat_s, lat_dir = _decimal_to_dms(self.latitude, True)
        lon_d, lon_m, lon_s, lon_dir = _decimal_to_dms(self.longitude, False)
        return lat_d, lat_m, lat_s, lat_dir, lon_d, lon_m, lon_s, lon_dir

    def to_status_data(self, estimated_speed_mps: Optional[float] = None) -> dict:
        """转换为主流程统一使用的机器人状态字段。"""
        velocity = self.actual_velocity_mps
        if velocity is None and estimated_speed_mps is not None:
            velocity = float(estimated_speed_mps)
        return {
            "robot_status": self.robot_status,
            "velocity": velocity,
            "azimuth": self.azimuth_x100 / 100.0 if self.has(FLAG_AZIMUTH) else None,
            "bat_voltage": self.battery_mv / 1000.0 if self.has(FLAG_BATTERY_VOLTAGE) else None,
            "soc": self.soc if self.has(FLAG_SOC) else None,
            "route_index": self.route_id if self.has(FLAG_ROUTE) else None,
            "waypoint_index": self.waypoint_id if self.has(FLAG_ROUTE) else None,
            "eyepoint_height": (
                self.camera_height_mm / 1000.0
                if self.has(FLAG_CAMERA_HEIGHT)
                else None
            ),
        }

    def to_tree_data(self) -> Optional[dict]:
        """返回果树字段；无数据源和当前无树是两种不同状态。"""
        if not self.has(FLAG_TREE):
            return None
        if self.current_tree_id:
            tree_code = f"ID{self.current_tree_id:04d}"
        elif self.left_tree_id or self.right_tree_id:
            tree_code = f"LID{self.left_tree_id:04d}/RID{self.right_tree_id:04d}"
        else:
            tree_code = ""
        return {
            "valid": True,
            "source": "telemetry",
            "current_tree_id": self.current_tree_id,
            "left_tree_id": self.left_tree_id,
            "right_tree_id": self.right_tree_id,
            "camera_side": self.camera_side,
            "tree_code": tree_code,
        }

    def to_dict(self) -> dict:
        data = asdict(self)
        data.update({
            "gps_valid": self.gps_valid,
            "longitude": self.longitude,
            "latitude": self.latitude,
            "altitude_m": self.altitude_m,
            "velocity_mps": self.actual_velocity_mps,
            "hdop": self.hdop_x100 / 100.0 if self.has(FLAG_GPS) else None,
        })
        return data


@dataclass(frozen=True)
class TelemetrySnapshot:
    """供检测线程原子读取的最新电控遥测快照。"""

    telemetry: Optional[RobotTelemetry]
    age_ms: Optional[int]
    stale: bool
    valid: bool
    estimated_speed_mps: Optional[float] = None

    @classmethod
    def empty(cls) -> "TelemetrySnapshot":
        return cls(None, None, True, False, None)

    def to_dms(self):
        if not self.valid or self.telemetry is None:
            return None
        return self.telemetry.to_dms()

    def to_status_data(self) -> dict:
        if not self.valid or self.telemetry is None:
            return {}
        return self.telemetry.to_status_data(self.estimated_speed_mps)

    def to_tree_data(self) -> Optional[dict]:
        if not self.valid or self.telemetry is None:
            return None
        return self.telemetry.to_tree_data()

    def to_dict(self) -> dict:
        if self.telemetry is None:
            return {
                "available": False,
                "valid": False,
                "stale": True,
                "age_ms": None,
                "estimated_speed_mps": None,
            }
        data = self.telemetry.to_dict()
        data.update({
            "available": True,
            "valid": self.valid,
            "stale": self.stale,
            "age_ms": self.age_ms,
            "estimated_speed_mps": self.estimated_speed_mps,
        })
        return data


class TelemetryStreamBuffer:
    """从任意串口字节块中恢复完整遥测包。"""

    def __init__(self, max_buffer_bytes: int = 4096):
        self.max_buffer_bytes = max(FRAME_SIZE * 2, int(max_buffer_bytes))
        self._buffer = bytearray()
        self.stats = {
            "discarded_bytes": 0,
            "length_errors": 0,
            "protocol_errors": 0,
            "checksum_errors": 0,
            "buffer_overflows": 0,
        }

    def feed(self, data: bytes, received_at_ms: Optional[int] = None) -> List[RobotTelemetry]:
        if data:
            self._buffer.extend(data)
        packets = []

        while True:
            header_index = self._buffer.find(FRAME_HEAD)
            if header_index < 0:
                self._discard_without_header()
                break
            if header_index > 0:
                del self._buffer[:header_index]
                self.stats["discarded_bytes"] += header_index
            if len(self._buffer) < 8:
                break

            payload_size = int.from_bytes(self._buffer[6:8], "big")
            if payload_size != PAYLOAD_SIZE:
                self.stats["length_errors"] += 1
                del self._buffer[0]
                continue

            frame_size = payload_size + 12
            if len(self._buffer) < frame_size:
                break

            candidate = bytes(self._buffer[:frame_size])
            try:
                telemetry = unpack_telemetry_packet(candidate, received_at_ms)
            except TelemetryChecksumError:
                self.stats["checksum_errors"] += 1
                del self._buffer[0]
                continue
            except TelemetryProtocolError:
                self.stats["protocol_errors"] += 1
                del self._buffer[0]
                continue

            del self._buffer[:frame_size]
            packets.append(telemetry)

        self._trim_overflow()
        return packets

    def clear(self):
        self._buffer.clear()

    def _discard_without_header(self):
        keep = 1 if self._buffer.endswith(FRAME_HEAD[:1]) else 0
        discarded = len(self._buffer) - keep
        if discarded > 0:
            del self._buffer[:discarded]
            self.stats["discarded_bytes"] += discarded

    def _trim_overflow(self):
        if len(self._buffer) <= self.max_buffer_bytes:
            return
        self.stats["buffer_overflows"] += 1
        last_header = self._buffer.rfind(FRAME_HEAD)
        if last_header >= 0 and len(self._buffer) - last_header <= self.max_buffer_bytes:
            del self._buffer[:last_header]
        else:
            self._buffer.clear()


def crc16_ccitt_false(data: bytes) -> int:
    """计算 CRC-16/CCITT-FALSE。"""
    crc = 0xFFFF
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def build_telemetry_packet(
    *,
    sequence: int,
    robot_id: int,
    robot_status: int,
    valid_flags: int,
    route_id: int = 0,
    waypoint_id: int = 0,
    current_tree_id: int = 0,
    left_tree_id: int = 0,
    right_tree_id: int = 0,
    camera_side: int = 0,
    gps_fix: int = 0,
    satellites: int = 0,
    hdop_x100: int = 0,
    longitude_e7: int = 0,
    latitude_e7: int = 0,
    altitude_cm: int = 0,
    timestamp: int = 0,
    azimuth_x100: int = 0,
    velocity_mm_s: int = 0,
    camera_height_mm: int = 0,
    battery_mv: int = 0,
    soc: int = 0,
    fault_code: int = 0,
) -> bytes:
    """按照文档规定的偏移生成一包遥测测试数据。"""
    values = {
        "sequence": sequence,
        "robot_id": robot_id,
        "robot_status": robot_status,
        "valid_flags": valid_flags,
        "route_id": route_id,
        "waypoint_id": waypoint_id,
        "current_tree_id": current_tree_id,
        "left_tree_id": left_tree_id,
        "right_tree_id": right_tree_id,
        "camera_side": camera_side,
        "gps_fix": gps_fix,
        "satellites": satellites,
        "hdop_x100": hdop_x100,
        "longitude_e7": longitude_e7,
        "latitude_e7": latitude_e7,
        "altitude_cm": altitude_cm,
        "timestamp": timestamp,
        "azimuth_x100": azimuth_x100,
        "velocity_mm_s": velocity_mm_s,
        "camera_height_mm": camera_height_mm,
        "battery_mv": battery_mv,
        "soc": soc,
        "fault_code": fault_code,
    }
    _validate_values(values)
    payload = PAYLOAD_STRUCT.pack(*[values[name] for name in _payload_field_names()])
    body = HEADER_STRUCT.pack(
        PROTOCOL_VERSION,
        MESSAGE_TYPE_TELEMETRY,
        sequence,
        PAYLOAD_SIZE,
    ) + payload
    checksum = crc16_ccitt_false(body)
    return FRAME_HEAD + body + checksum.to_bytes(2, "big") + FRAME_TAIL


def unpack_telemetry_packet(
    packet: bytes,
    received_at_ms: Optional[int] = None,
) -> RobotTelemetry:
    """校验并解析固定 58 字节遥测包。"""
    if len(packet) != FRAME_SIZE:
        raise TelemetryProtocolError(f"数据包长度错误: {len(packet)}，期望 {FRAME_SIZE}")
    if packet[:2] != FRAME_HEAD:
        raise TelemetryProtocolError("帧头错误")
    if packet[-2:] != FRAME_TAIL:
        raise TelemetryProtocolError("帧尾错误")

    version, message_type, sequence, payload_size = HEADER_STRUCT.unpack(packet[2:8])
    if version != PROTOCOL_VERSION:
        raise TelemetryProtocolError(f"不支持的协议版本: {version}")
    if message_type != MESSAGE_TYPE_TELEMETRY:
        raise TelemetryProtocolError(f"不支持的消息类型: {message_type}")
    if payload_size != PAYLOAD_SIZE:
        raise TelemetryProtocolError(f"数据区长度错误: {payload_size}")

    received_checksum = int.from_bytes(packet[54:56], "big")
    calculated_checksum = crc16_ccitt_false(packet[2:54])
    if received_checksum != calculated_checksum:
        raise TelemetryChecksumError(
            f"CRC16 错误: 收到 {received_checksum:04X}，计算 {calculated_checksum:04X}"
        )

    unpacked = PAYLOAD_STRUCT.unpack(packet[8:54])
    values = dict(zip(_payload_field_names(), unpacked))
    values["sequence"] = sequence
    _validate_values(values)
    if received_at_ms is None:
        received_at_ms = time.time_ns() // 1_000_000
    return RobotTelemetry(received_at_ms=int(received_at_ms), **values)


def _payload_field_names() -> Tuple[str, ...]:
    return (
        "robot_id",
        "robot_status",
        "valid_flags",
        "route_id",
        "waypoint_id",
        "current_tree_id",
        "left_tree_id",
        "right_tree_id",
        "camera_side",
        "gps_fix",
        "satellites",
        "hdop_x100",
        "longitude_e7",
        "latitude_e7",
        "altitude_cm",
        "timestamp",
        "azimuth_x100",
        "velocity_mm_s",
        "camera_height_mm",
        "battery_mv",
        "soc",
        "fault_code",
    )


def _validate_values(values: dict):
    def require_range(name, minimum, maximum):
        value = int(values[name])
        if not minimum <= value <= maximum:
            raise TelemetryProtocolError(
                f"字段 {name} 超出范围 {minimum}~{maximum}: {value}"
            )

    require_range("sequence", 0, 0xFFFF)
    require_range("robot_id", 1, 0xFF)
    if values["robot_status"] not in VALID_ROBOT_STATUSES:
        raise TelemetryProtocolError(f"未知机器人状态: {values['robot_status']}")
    require_range("valid_flags", 0, DEFINED_FLAGS_MASK)
    if values["valid_flags"] & ~DEFINED_FLAGS_MASK:
        raise TelemetryProtocolError("valid_flags 使用了保留位")

    for name in (
        "route_id", "waypoint_id", "current_tree_id", "left_tree_id",
        "right_tree_id", "hdop_x100", "azimuth_x100", "velocity_mm_s",
        "camera_height_mm", "battery_mv", "fault_code",
    ):
        require_range(name, 0, 0xFFFF)
    for name in ("camera_side", "gps_fix", "satellites", "soc"):
        require_range(name, 0, 0xFF)
    require_range("longitude_e7", -1_800_000_000, 1_800_000_000)
    require_range("latitude_e7", -900_000_000, 900_000_000)
    require_range("altitude_cm", -0x80000000, 0x7FFFFFFF)
    require_range("timestamp", 0, 0xFFFFFFFF)

    flags = values["valid_flags"]
    if values["camera_side"] not in {0, 1, 2}:
        raise TelemetryProtocolError(f"未知拍摄侧: {values['camera_side']}")
    if values["gps_fix"] not in VALID_GPS_FIXES:
        raise TelemetryProtocolError(f"未知 GPS 定位质量: {values['gps_fix']}")
    if values["azimuth_x100"] > 35999:
        raise TelemetryProtocolError("方位角必须小于 360.00 度")
    if values["soc"] > 100:
        raise TelemetryProtocolError("SOC 必须在 0~100 范围")
    if values["hdop_x100"] > 9999:
        raise TelemetryProtocolError("HDOP 必须在 0~99.99 范围")

    _require_zero_when_invalid(values, flags, FLAG_ROUTE, ("route_id", "waypoint_id"))
    _require_zero_when_invalid(
        values,
        flags,
        FLAG_TREE,
        ("current_tree_id", "left_tree_id", "right_tree_id", "camera_side"),
    )
    _require_zero_when_invalid(
        values,
        flags,
        FLAG_GPS,
        ("gps_fix", "satellites", "hdop_x100", "longitude_e7", "latitude_e7", "altitude_cm"),
    )
    _require_zero_when_invalid(values, flags, FLAG_TIMESTAMP, ("timestamp",))
    _require_zero_when_invalid(values, flags, FLAG_AZIMUTH, ("azimuth_x100",))
    _require_zero_when_invalid(values, flags, FLAG_VELOCITY, ("velocity_mm_s",))
    _require_zero_when_invalid(values, flags, FLAG_CAMERA_HEIGHT, ("camera_height_mm",))
    _require_zero_when_invalid(values, flags, FLAG_BATTERY_VOLTAGE, ("battery_mv",))
    _require_zero_when_invalid(values, flags, FLAG_SOC, ("soc",))
    _require_zero_when_invalid(values, flags, FLAG_FAULT, ("fault_code",))

    if flags & FLAG_GPS and values["gps_fix"] not in VALID_POSITION_FIXES:
        raise TelemetryProtocolError("GPS 有效位为 1 时 gps_fix 必须表示有效定位")
    if flags & FLAG_TREE:
        side = values["camera_side"]
        current = values["current_tree_id"]
        if side == 0 and current != 0:
            raise TelemetryProtocolError("拍摄侧未知时 current_tree_id 必须为 0")
        if side == 1 and current != values["left_tree_id"]:
            raise TelemetryProtocolError("左侧拍摄时当前树必须等于左树编号")
        if side == 2 and current != values["right_tree_id"]:
            raise TelemetryProtocolError("右侧拍摄时当前树必须等于右树编号")


def _require_zero_when_invalid(values, flags, flag, field_names):
    if flags & flag:
        return
    nonzero = [name for name in field_names if values[name] != 0]
    if nonzero:
        raise TelemetryProtocolError(
            f"有效位未设置时字段必须为 0: {', '.join(nonzero)}"
        )


def _decimal_to_dms(value: float, is_latitude: bool):
    if value is None or not math.isfinite(float(value)):
        raise TelemetryProtocolError("GPS 坐标不是有限数值")
    direction = "N" if is_latitude else "E"
    if value < 0:
        direction = "S" if is_latitude else "W"
    absolute = abs(float(value))
    degree = int(absolute)
    minute_value = (absolute - degree) * 60.0
    minute = int(minute_value)
    second = round((minute_value - minute) * 60.0, 2)
    if second >= 60.0:
        second = 0.0
        minute += 1
    if minute >= 60:
        minute = 0
        degree += 1
    return degree, minute, second, direction


assert PAYLOAD_STRUCT.size == PAYLOAD_SIZE
