"""GPS 串口文本协议定义与解析工具。"""

from dataclasses import asdict, dataclass
import math
import time
from typing import List, Optional, Tuple, Union


PROTOCOL_NAME = "OPGPS"
PROTOCOL_VERSION = "V1"
VALID_FIX_QUALITIES = {0, 1, 2, 4, 5}
EARTH_RADIUS_M = 6371008.8


class GpsProtocolError(ValueError):
    """GPS 报文格式错误。"""


class GpsChecksumError(GpsProtocolError):
    """GPS 报文校验失败。"""


@dataclass(frozen=True)
class GpsFix:
    """一条已经通过协议校验的 GPS 数据。"""

    protocol_version: str
    robot_id: str
    sequence: int
    longitude: float
    latitude: float
    altitude_m: float
    fix_quality: int
    satellites: int
    hdop: float
    received_at_ms: int

    @property
    def position_valid(self) -> bool:
        return self.fix_quality != 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GpsSnapshot:
    """供检测线程读取的 GPS 快照。"""

    fix: Optional[GpsFix]
    age_ms: Optional[int]
    stale: bool
    valid: bool
    speed_mps: Optional[float] = None

    @classmethod
    def empty(cls) -> "GpsSnapshot":
        return cls(fix=None, age_ms=None, stale=True, valid=False, speed_mps=None)

    def to_dict(self) -> dict:
        if self.fix is None:
            return {
                "available": False,
                "valid": False,
                "stale": True,
                "age_ms": None,
                "protocol_version": None,
                "robot_id": None,
                "sequence": None,
                "longitude": None,
                "latitude": None,
                "altitude_m": None,
                "fix_quality": None,
                "satellites": None,
                "hdop": None,
                "received_at_ms": None,
                "speed_mps": None,
            }

        data = self.fix.to_dict()
        data.update({
            "available": True,
            "valid": self.valid,
            "stale": self.stale,
            "age_ms": self.age_ms,
            "speed_mps": self.speed_mps,
        })
        return data

    def to_dms(self) -> Tuple[int, int, float, str, int, int, float, str]:
        """转换为现有 HTTP/UDP 上报使用的度分秒格式。"""
        if not self.valid or self.fix is None:
            return 0, 0, 0.0, "N", 0, 0, 0.0, "E"

        lat_d, lat_m, lat_s, lat_dir = decimal_degrees_to_dms(
            self.fix.latitude, is_latitude=True
        )
        lon_d, lon_m, lon_s, lon_dir = decimal_degrees_to_dms(
            self.fix.longitude, is_latitude=False
        )
        return lat_d, lat_m, lat_s, lat_dir, lon_d, lon_m, lon_s, lon_dir


class GpsLineBuffer:
    """按换行符从任意串口字节块中恢复完整报文。"""

    def __init__(self, max_buffer_bytes: int = 4096):
        self.max_buffer_bytes = max(128, int(max_buffer_bytes))
        self._buffer = bytearray()
        self.overflow_count = 0

    def feed(self, data: bytes) -> List[bytes]:
        if not data:
            return []

        self._buffer.extend(data)
        lines = []
        while True:
            newline_index = self._buffer.find(b"\n")
            if newline_index < 0:
                break
            line = bytes(self._buffer[:newline_index]).rstrip(b"\r")
            del self._buffer[:newline_index + 1]
            if line:
                lines.append(line)

        if len(self._buffer) > self.max_buffer_bytes:
            self.overflow_count += 1
            last_start = self._buffer.rfind(b"$")
            if last_start >= 0 and len(self._buffer) - last_start <= self.max_buffer_bytes:
                self._buffer = self._buffer[last_start:]
            else:
                self._buffer.clear()

        return lines

    def clear(self):
        self._buffer.clear()


def calculate_checksum(payload: Union[str, bytes]) -> int:
    """计算 NMEA 风格的逐字节异或校验。"""
    raw = payload.encode("ascii") if isinstance(payload, str) else payload
    checksum = 0
    for value in raw:
        checksum ^= value
    return checksum


def great_circle_distance_m(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """计算两个十进制度坐标之间的地表距离，单位为米。"""
    latitude_a_rad = math.radians(float(latitude_a))
    latitude_b_rad = math.radians(float(latitude_b))
    latitude_delta = latitude_b_rad - latitude_a_rad
    longitude_delta = math.radians(float(longitude_b) - float(longitude_a))
    haversine = (
        math.sin(latitude_delta / 2.0) ** 2
        + math.cos(latitude_a_rad)
        * math.cos(latitude_b_rad)
        * math.sin(longitude_delta / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(haversine)))


def parse_gps_sentence(
    sentence: Union[str, bytes],
    received_at_ms: Optional[int] = None,
) -> GpsFix:
    """解析并校验一条 ``$OPGPS`` 报文。"""
    if isinstance(sentence, bytes):
        try:
            text = sentence.decode("ascii")
        except UnicodeDecodeError as exc:
            raise GpsProtocolError("报文不是有效 ASCII 数据") from exc
    else:
        text = str(sentence)

    text = text.rstrip("\r\n")
    if not text.startswith("$"):
        raise GpsProtocolError("报文缺少起始符 $")
    if "*" not in text:
        raise GpsProtocolError("报文缺少校验分隔符 *")

    body, checksum_text = text[1:].rsplit("*", 1)
    if len(checksum_text) != 2:
        raise GpsProtocolError("校验码必须是两位十六进制字符")
    try:
        received_checksum = int(checksum_text, 16)
    except ValueError as exc:
        raise GpsProtocolError("校验码不是有效十六进制字符") from exc

    calculated_checksum = calculate_checksum(body)
    if received_checksum != calculated_checksum:
        raise GpsChecksumError(
            f"校验失败: 收到 {received_checksum:02X}, 计算 {calculated_checksum:02X}"
        )

    fields = body.split(",")
    if len(fields) != 10:
        raise GpsProtocolError(f"字段数量错误: 收到 {len(fields)}, 期望 10")
    if fields[0] != PROTOCOL_NAME:
        raise GpsProtocolError(f"协议名称错误: {fields[0]}")
    if fields[1] != PROTOCOL_VERSION:
        raise GpsProtocolError(f"不支持的协议版本: {fields[1]}")

    robot_id = fields[2].strip()
    if not robot_id:
        raise GpsProtocolError("机器人 ID 不能为空")

    try:
        sequence = int(fields[3])
        longitude = float(fields[4])
        latitude = float(fields[5])
        altitude_m = float(fields[6])
        fix_quality = int(fields[7])
        satellites = int(fields[8])
        hdop = float(fields[9])
    except ValueError as exc:
        raise GpsProtocolError("报文包含无法解析的数值字段") from exc

    if not 0 <= sequence <= 0xFFFFFFFF:
        raise GpsProtocolError("序号超出 0~4294967295 范围")
    if not math.isfinite(longitude) or not -180.0 <= longitude <= 180.0:
        raise GpsProtocolError("经度超出 -180~180 范围")
    if not math.isfinite(latitude) or not -90.0 <= latitude <= 90.0:
        raise GpsProtocolError("纬度超出 -90~90 范围")
    if not math.isfinite(altitude_m):
        raise GpsProtocolError("海拔不是有效有限数值")
    if fix_quality not in VALID_FIX_QUALITIES:
        raise GpsProtocolError(f"不支持的定位类型: {fix_quality}")
    if not 0 <= satellites <= 255:
        raise GpsProtocolError("卫星数超出 0~255 范围")
    if not math.isfinite(hdop) or not 0.0 <= hdop <= 99.99:
        raise GpsProtocolError("HDOP 超出 0~99.99 范围")

    if received_at_ms is None:
        received_at_ms = time.time_ns() // 1_000_000

    return GpsFix(
        protocol_version=fields[1],
        robot_id=robot_id,
        sequence=sequence,
        longitude=longitude,
        latitude=latitude,
        altitude_m=altitude_m,
        fix_quality=fix_quality,
        satellites=satellites,
        hdop=hdop,
        received_at_ms=int(received_at_ms),
    )


def decimal_degrees_to_dms(
    decimal_value: float,
    is_latitude: bool,
) -> Tuple[int, int, float, str]:
    """将带符号十进制度转换为保留两位秒小数的度分秒。"""
    direction = "N" if is_latitude else "E"
    if decimal_value < 0:
        direction = "S" if is_latitude else "W"

    absolute = abs(float(decimal_value))
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


def select_frame_gps_dms(
    gps_enabled: bool,
    gps_snapshot: Optional[GpsSnapshot],
    fallback_dms: Tuple[int, int, float, str, int, int, float, str],
) -> Tuple[int, int, float, str, int, int, float, str]:
    """按 GPS 开关和有效性选择当前帧的对外度分秒坐标。"""
    if not gps_enabled:
        return fallback_dms
    if gps_snapshot is None:
        return 0, 0, 0.0, "N", 0, 0, 0.0, "E"
    return gps_snapshot.to_dms()
