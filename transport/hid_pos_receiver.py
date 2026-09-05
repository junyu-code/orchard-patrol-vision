"""双路 HID POS 标签扫描器接收与果树编号解析。"""

from dataclasses import dataclass
import os
import re
import threading
import time
from typing import Callable, Dict, Mapping, Optional, Pattern, Tuple

try:
    import hid
except ImportError:
    hid = None

if os.name == "nt":
    try:
        from winrt.runtime import MTA, init_apartment, uninit_apartment
        from winrt.windows.devices.pointofservice import BarcodeScanner
    except ImportError:
        MTA = None
        init_apartment = None
        uninit_apartment = None
        BarcodeScanner = None
else:
    MTA = None
    init_apartment = None
    uninit_apartment = None
    BarcodeScanner = None


HID_POS_USAGE_PAGE = 0x8C
HID_POS_USAGE = 0x02
EM22_REPORT_ID = 0x02
EM22_MAX_DATA_BYTES = 56
EM22_REPORT_SIZE = 64
TREE_SIDES = ("left", "right")
DEFAULT_TAG_PATTERN = r"^(?:TREE[:_-]?)?(?P<tree_id>\d{1,5})$"
WINDOWS_POS_INTERFACE_GUID = "c243ffbd-3afc-45e9-b3d3-2ba18bc7ebc5"


class HidPosProtocolError(ValueError):
    """HID POS 输入报告或标签内容不符合约定。"""


class _WindowsPosConnection:
    """保存 Windows POS API 对象和事件句柄。"""

    def __init__(self, scanner, claimed, data_token, data_handler):
        self.scanner = scanner
        self.claimed = claimed
        self.data_token = data_token
        # WinRT 事件回调需要持有强引用，避免被 Python 回收。
        self.data_handler = data_handler

    def close(self):
        try:
            self.claimed.remove_data_received(self.data_token)
        except Exception:
            pass
        try:
            self.claimed.disable_async().wait(0.5)
        except Exception:
            pass
        try:
            self.claimed.close()
        except Exception:
            pass
        try:
            self.scanner.close()
        except Exception:
            pass


@dataclass(frozen=True)
class HidTagReading:
    """单次有效标签读取结果。"""

    side: str
    tree_id: int
    raw_text: str
    serial_number: str
    received_at_ms: int


@dataclass(frozen=True)
class HidTagSideSnapshot:
    """单侧扫描器的最新不可变快照。"""

    reading: Optional[HidTagReading]
    age_ms: Optional[int]
    stale: bool
    valid: bool

    @classmethod
    def empty(cls):
        return cls(reading=None, age_ms=None, stale=False, valid=False)

    @property
    def tree_id(self) -> Optional[int]:
        return self.reading.tree_id if self.valid and self.reading else None


@dataclass(frozen=True)
class HidTagSnapshot:
    """左右两台扫描器在同一时刻的快照。"""

    left: HidTagSideSnapshot
    right: HidTagSideSnapshot

    @classmethod
    def empty(cls):
        return cls(HidTagSideSnapshot.empty(), HidTagSideSnapshot.empty())

    @property
    def has_valid_tag(self) -> bool:
        return self.left.valid or self.right.valid


def decode_em22_hid_pos_report(report) -> bytes:
    """按 EM22 HID 描述符中的 Byte Count 提取条码数据区。"""
    raw = bytes(report or b"")
    if not raw:
        return b""

    # 纯 HID POS 报告：Report ID(1) + Byte Count(1) + 条码数据(56) + 扩展区(6)。
    if raw[0] == EM22_REPORT_ID:
        if len(raw) < 2:
            raise HidPosProtocolError("HID POS 报告缺少数据长度")
        data_length = raw[1]
        data_offset = 2
    else:
        # 某些 hidraw 后端会去掉 Report ID，此时 Byte Count 位于首字节。
        data_length = raw[0]
        data_offset = 1

    if data_length > EM22_MAX_DATA_BYTES:
        raise HidPosProtocolError(
            f"HID POS 数据长度超出范围：{data_length} > {EM22_MAX_DATA_BYTES}"
        )
    if len(raw) < data_offset + data_length:
        raise HidPosProtocolError(
            f"HID POS 报告被截断：需要 {data_offset + data_length} 字节，"
            f"实际 {len(raw)} 字节"
        )
    return raw[data_offset:data_offset + data_length]


def parse_tree_tag(text: str, pattern: Pattern[str]) -> int:
    """把纯数字或 TREE:数字 标签转换为 uint16 果树编号。"""
    normalized = str(text or "").strip().upper()
    match = pattern.fullmatch(normalized)
    if match is None:
        raise HidPosProtocolError(f"标签格式无效：{text!r}")

    groups = match.groupdict()
    if "tree_id" in groups:
        value = groups["tree_id"]
    elif match.lastindex:
        value = match.group(1)
    else:
        value = match.group(0)
    try:
        tree_id = int(value)
    except (TypeError, ValueError) as exc:
        raise HidPosProtocolError(f"标签未包含有效果树编号：{text!r}") from exc
    if not 1 <= tree_id <= 65535:
        raise HidPosProtocolError(f"果树编号超出范围：{tree_id}")
    return tree_id


def merge_hid_tag_tree_data(
    base_tree_data: Optional[Mapping],
    tag_snapshot: Optional[HidTagSnapshot],
    hid_only: bool = False,
) -> Optional[dict]:
    """合并扫码树号；有效扫码覆盖对应侧，其余字段保留基础数据。"""
    snapshot = tag_snapshot or HidTagSnapshot.empty()
    active = []
    stale_sides = []
    for side in TREE_SIDES:
        side_snapshot = getattr(snapshot, side)
        if side_snapshot.valid and side_snapshot.reading is not None:
            active.append((side, side_snapshot.reading))
        elif side_snapshot.stale and side_snapshot.reading is not None:
            stale_sides.append(side)

    if not active:
        if stale_sides:
            # 已经收到过二维码但超过有效期时，不能回退到可能仍保存旧编号的
            # 遥测/时间轴数据；上传明确的无树状态。
            if base_tree_data is None and not hid_only:
                return None
            result = {} if hid_only else dict(base_tree_data or {})
            result.update(
                {
                    "current_tree_id": 0,
                    "left_tree_id": 0,
                    "right_tree_id": 0,
                    "camera_side": 0,
                    "source": (
                        "hid_pos"
                        if hid_only or base_tree_data is None
                        else "mixed_hid_pos"
                    ),
                    "tag_serials": {},
                }
            )
            if "tree_code" in result:
                result["tree_code"] = ""
            if "tree_id" in result:
                result["tree_id"] = 0
            return result
        if hid_only:
            return {
                "current_tree_id": 0,
                "left_tree_id": 0,
                "right_tree_id": 0,
                "camera_side": 0,
                "source": "hid_pos",
                "tag_serials": {},
            }
        return dict(base_tree_data) if base_tree_data is not None else None

    result = {} if hid_only else dict(base_tree_data or {})
    result.setdefault("left_tree_id", 0)
    result.setdefault("right_tree_id", 0)
    for side, reading in active:
        result[f"{side}_tree_id"] = reading.tree_id
    for side in stale_sides:
        result[f"{side}_tree_id"] = 0

    latest_side, latest_reading = max(
        active,
        key=lambda item: (item[1].received_at_ms, item[0] == "right"),
    )
    result["current_tree_id"] = latest_reading.tree_id
    result["camera_side"] = 1 if latest_side == "left" else 2
    result["source"] = (
        "hid_pos"
        if hid_only or base_tree_data is None
        else "mixed_hid_pos"
    )
    result["tag_serials"] = {
        side: reading.serial_number for side, reading in active
    }
    return result


def select_tree_id_data(
    telemetry_tree_data: Optional[Mapping],
    tag_snapshot: Optional[HidTagSnapshot],
    use_hid_tags: bool,
) -> Optional[dict]:
    """选择树号来源；有效扫码覆盖基础数据，过期扫码按无树处理。"""
    if use_hid_tags:
        return merge_hid_tag_tree_data(
            telemetry_tree_data,
            tag_snapshot,
            hid_only=False,
        )
    return (
        dict(telemetry_tree_data)
        if telemetry_tree_data is not None
        else None
    )


class DualHidPosReceiver:
    """按硬件序列号绑定左右扫描器，并在后台维护最新标签。"""

    def __init__(
        self,
        left_serial: str,
        right_serial: str,
        vendor_id: int = 0x1EAB,
        product_id: int = 0x0010,
        stale_timeout: float = 30 * 60.0,
        duplicate_interval: float = 0.3,
        reconnect_interval: float = 2.0,
        poll_interval: float = 0.01,
        encoding: str = "utf-8",
        tag_pattern: str = DEFAULT_TAG_PATTERN,
        hid_backend=None,
        clock_ms: Optional[Callable[[], int]] = None,
    ):
        self.serial_by_side = {
            "left": self._normalize_serial(left_serial),
            "right": self._normalize_serial(right_serial),
        }
        if not all(self.serial_by_side.values()):
            raise ValueError("左右 HID POS 扫描器都必须配置硬件序列号")
        if self.serial_by_side["left"] == self.serial_by_side["right"]:
            raise ValueError("左右 HID POS 扫描器不能使用相同序列号")

        self.vendor_id = int(vendor_id)
        self.product_id = int(product_id)
        self.stale_timeout_ms = max(1, int(float(stale_timeout) * 1000))
        self.duplicate_interval_ms = max(0, int(float(duplicate_interval) * 1000))
        self.reconnect_interval = max(0.1, float(reconnect_interval))
        self.poll_interval = max(0.001, float(poll_interval))
        self.encoding = str(encoding or "utf-8")
        try:
            self.tag_pattern = re.compile(tag_pattern, re.IGNORECASE)
        except re.error as exc:
            raise ValueError(f"HID 标签正则表达式无效：{exc}") from exc

        if hid_backend is None and hid is None:
            raise RuntimeError("HID POS 接收需要安装 hidapi>=0.14.0")
        if os.name == "nt" and hid_backend is None and BarcodeScanner is None:
            raise RuntimeError(
                "Windows HID POS 接收需要安装 "
                "winrt-Windows.Devices.PointOfService>=3.2.1"
            )
        self.hid_backend = hid_backend or hid
        self._use_windows_pos = os.name == "nt" and hid_backend is None
        self.clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None
        self._connections: Dict[str, object] = {}
        self._latest: Dict[str, Optional[HidTagReading]] = {
            "left": None,
            "right": None,
        }
        self._last_error_log_at: Dict[str, float] = {}
        self._stats = {
            "enumeration_cycles": 0,
            "connections": 0,
            "disconnects": 0,
            "reports": 0,
            "valid_tags": 0,
            "duplicate_tags": 0,
            "invalid_reports": 0,
            "invalid_tags": 0,
        }

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def active_sides(self) -> Tuple[str, ...]:
        with self._lock:
            return tuple(side for side in TREE_SIDES if side in self._connections)

    def start(self):
        """启动后台枚举和读取线程；重复调用不会创建多个线程。"""
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="dual-hid-pos-receiver",
            daemon=True,
        )
        self._thread.start()

    def stop(self, join_timeout: float = 2.0):
        """停止读取并关闭所有 HID 句柄。"""
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=max(0.1, float(join_timeout)))
        self._close_all()
        self._thread = None

    def get_snapshot(self, now_ms: Optional[int] = None) -> HidTagSnapshot:
        """返回左右两侧标签的线程安全不可变快照。"""
        current_ms = int(self.clock_ms() if now_ms is None else now_ms)
        with self._lock:
            readings = dict(self._latest)

        snapshots = {}
        for side in TREE_SIDES:
            reading = readings[side]
            if reading is None:
                snapshots[side] = HidTagSideSnapshot.empty()
                continue
            age_ms = max(0, current_ms - reading.received_at_ms)
            stale = age_ms >= self.stale_timeout_ms
            snapshots[side] = HidTagSideSnapshot(
                reading=reading,
                age_ms=age_ms,
                stale=stale,
                valid=not stale,
            )
        return HidTagSnapshot(
            left=snapshots["left"],
            right=snapshots["right"],
        )

    def get_stats(self) -> dict:
        with self._lock:
            return dict(self._stats)

    def enumerate_bound_devices(self) -> dict:
        """枚举并绑定左右 HID POS 接口，供启动和现场自检复用。

        部分 Linux hidraw 驱动不会返回 USB serial_number，也可能省略
        usage/product 描述。此时在已经按 VID/PID 过滤的设备中按路径排序，
        将两台设备稳定分配给左右两侧。
        """
        found = {}
        devices = self.hid_backend.enumerate(self.vendor_id, self.product_id) or []
        self._increment_stat("enumeration_cycles")
        candidates = []
        for device_info in devices:
            if not self._is_pos_interface(device_info):
                continue
            candidates.append(device_info)
            serial_number = self._normalize_serial(device_info.get("serial_number"))
            for side, expected_serial in self.serial_by_side.items():
                if serial_number == expected_serial and side not in found:
                    found[side] = device_info

        # Linux 上常见 serial_number 为空；按物理 USB 拓扑路径排序，保证
        # 同一组端口每次枚举顺序一致。若能匹配到一侧，只补另一侧。
        unbound_sides = [side for side in TREE_SIDES if side not in found]
        unbound_devices = [
            device for device in sorted(candidates, key=self._device_path_key)
            if device not in found.values()
        ]
        if unbound_devices and unbound_sides:
            for side, device_info in zip(unbound_sides, unbound_devices):
                found[side] = device_info
                if not self._normalize_serial(device_info.get("serial_number")):
                    print(
                        f"[HID标签] {self._side_label(side)}设备无序列号，"
                        f"按路径绑定：{self._device_path_text(device_info.get('path'))}"
                    )
        return found

    def _run(self):
        if self._use_windows_pos:
            self._run_windows_pos()
            return

        self._run_hidapi()

    def _run_hidapi(self):
        """Linux 等平台直接从 hidraw 读取输入报告。"""
        next_enumeration_at = 0.0
        while not self._stop_event.is_set():
            now = time.monotonic()
            if now >= next_enumeration_at:
                self._connect_missing()
                next_enumeration_at = now + self.reconnect_interval

            for side, connection in self._connection_items():
                try:
                    report = connection.read(64)
                    if report:
                        self._handle_report(side, report)
                except Exception as exc:
                    self._log_error_limited(side, f"读取失败：{exc}")
                    self._close_side(side, disconnected=True)
            self._stop_event.wait(self.poll_interval)
        self._close_all()

    def _run_windows_pos(self):
        """Windows 通过系统 BarcodeScanner API 接收 POS 数据。"""
        apartment_initialized = False
        try:
            init_apartment(MTA)
            apartment_initialized = True
            while not self._stop_event.is_set():
                self._connect_missing_windows()
                self._stop_event.wait(self.reconnect_interval)
        except Exception as exc:
            self._log_error_limited("windows", f"Windows POS 后端异常：{exc}")
        finally:
            self._close_all()
            if apartment_initialized:
                try:
                    uninit_apartment()
                except Exception:
                    pass

    def _connect_missing(self):
        try:
            found = self.enumerate_bound_devices()
        except Exception as exc:
            self._log_error_limited("enumerate", f"枚举设备失败：{exc}")
            return

        active = set(self.active_sides)
        for side in TREE_SIDES:
            if side in active:
                continue
            device_info = found.get(side)
            if device_info is None:
                self._log_error_limited(
                    side,
                    f"未发现序列号 {self.serial_by_side[side]} 的 HID POS 设备",
                )
                continue
            connection = None
            try:
                connection = self.hid_backend.device()
                connection.open_path(device_info["path"])
                connection.set_nonblocking(True)
                with self._lock:
                    self._connections[side] = connection
                    self._stats["connections"] += 1
                print(
                    f"[HID标签] {self._side_label(side)}设备已连接："
                    f"{self.serial_by_side[side]}"
                )
            except Exception as exc:
                if connection is not None:
                    try:
                        connection.close()
                    except Exception:
                        pass
                self._log_error_limited(side, f"打开设备失败：{exc}")

    def _connect_missing_windows(self):
        try:
            found = self.enumerate_bound_devices()
        except Exception as exc:
            self._log_error_limited("enumerate", f"枚举设备失败：{exc}")
            return

        active = set(self.active_sides)
        for side in active - set(found):
            self._close_side(side, disconnected=True)
        for side in TREE_SIDES:
            if side in active or side not in found:
                if side not in found:
                    self._log_error_limited(
                        side,
                        f"未发现序列号 {self.serial_by_side[side]} 的 HID POS 设备",
                    )
                continue
            scanner = None
            claimed = None
            try:
                device_id = self._windows_pos_device_id(found[side]["path"])
                scanner = BarcodeScanner.from_id_async(device_id).get()
                if scanner is None:
                    raise RuntimeError("Windows 未能创建设备对象")
                claimed = scanner.claim_scanner_async().get()
                if claimed is None:
                    raise RuntimeError("Windows 未能领取设备")

                def data_handler(_sender, args, scanner_side=side):
                    try:
                        report = args.report
                        data = bytes(report.scan_data_label)
                        if not data:
                            data = bytes(report.scan_data)
                        self._handle_barcode_data(scanner_side, data)
                    except Exception as exc:
                        self._increment_stat("invalid_reports")
                        self._log_error_limited(
                            scanner_side,
                            f"Windows POS 数据处理失败：{exc}",
                        )

                data_token = claimed.add_data_received(data_handler)
                claimed.is_decode_data_enabled = True
                claimed.is_disabled_on_data_received = False
                claimed.enable_async().get()
                connection = _WindowsPosConnection(
                    scanner=scanner,
                    claimed=claimed,
                    data_token=data_token,
                    data_handler=data_handler,
                )
                with self._lock:
                    self._connections[side] = connection
                    self._stats["connections"] += 1
                print(
                    f"[HID标签] {self._side_label(side)}设备已由 Windows POS API 领取："
                    f"{self.serial_by_side[side]}"
                )
            except Exception as exc:
                if claimed is not None:
                    try:
                        claimed.close()
                    except Exception:
                        pass
                if scanner is not None:
                    try:
                        scanner.close()
                    except Exception:
                        pass
                self._log_error_limited(side, f"Windows POS 设备打开失败：{exc}")

    def _handle_report(self, side: str, report) -> bool:
        self._increment_stat("reports")
        try:
            barcode_data = decode_em22_hid_pos_report(report)
        except HidPosProtocolError as exc:
            self._increment_stat("invalid_reports")
            self._log_error_limited(side, str(exc))
            return False
        if not barcode_data:
            return False

        return self._handle_barcode_data(side, barcode_data)

    def _handle_barcode_data(self, side: str, barcode_data: bytes) -> bool:
        """解析 Windows POS API 或 hidraw 提供的条码数据。"""

        try:
            text = barcode_data.decode(self.encoding).strip("\x00\r\n ")
        except UnicodeDecodeError as exc:
            self._increment_stat("invalid_tags")
            self._log_error_limited(side, f"标签编码无效：{exc}")
            return False
        try:
            tree_id = parse_tree_tag(text, self.tag_pattern)
        except HidPosProtocolError as exc:
            self._increment_stat("invalid_tags")
            self._log_error_limited(side, str(exc))
            return False

        received_at_ms = int(self.clock_ms())
        reading = HidTagReading(
            side=side,
            tree_id=tree_id,
            raw_text=text,
            serial_number=self.serial_by_side[side],
            received_at_ms=received_at_ms,
        )
        with self._lock:
            previous = self._latest[side]
            if (
                previous is not None
                and previous.tree_id == tree_id
                and received_at_ms - previous.received_at_ms
                <= self.duplicate_interval_ms
            ):
                self._stats["duplicate_tags"] += 1
                return False
            self._latest[side] = reading
            self._stats["valid_tags"] += 1
        print(
            f"[HID标签] {self._side_label(side)}扫码："
            f"ID{tree_id:04d} ({self.serial_by_side[side]})"
        )
        return True

    def _connection_items(self):
        with self._lock:
            return tuple(self._connections.items())

    def _close_side(self, side: str, disconnected: bool = False):
        with self._lock:
            connection = self._connections.pop(side, None)
            if disconnected and connection is not None:
                self._stats["disconnects"] += 1
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

    def _close_all(self):
        for side in TREE_SIDES:
            self._close_side(side)

    def _increment_stat(self, name: str, amount: int = 1):
        with self._lock:
            self._stats[name] += amount

    def _log_error_limited(self, key: str, message: str):
        now = time.monotonic()
        previous = self._last_error_log_at.get(key, 0.0)
        if now - previous >= 5.0:
            print(f"[HID标签] {self._side_label(key)}{message}")
            self._last_error_log_at[key] = now

    @staticmethod
    def _is_pos_interface(device_info: Mapping) -> bool:
        usage_page = device_info.get("usage_page")
        usage = device_info.get("usage")
        if usage_page == HID_POS_USAGE_PAGE and usage == HID_POS_USAGE:
            return True
        product = str(device_info.get("product_string") or "").strip().upper()
        interface_number = device_info.get("interface_number")
        if "HID POS" in product and interface_number in (None, 0, 1):
            return True
        # hidapi 在部分 Linux hidraw 后端会把描述字段全部返回为空；
        # enumerate() 已按本接收器的 EM22 VID/PID 过滤，接口 0/1 可直接使用。
        return not product and interface_number in (None, 0, 1)

    @staticmethod
    def _device_path_text(path) -> str:
        if isinstance(path, bytes):
            return path.decode("utf-8", errors="replace")
        return str(path or "")

    @classmethod
    def _device_path_key(cls, device_info: Mapping) -> str:
        return cls._device_path_text(device_info.get("path"))

    @staticmethod
    def _windows_pos_device_id(hid_path) -> str:
        """把 hidapi 路径转换为 Windows BarcodeScanner 设备路径。"""
        if isinstance(hid_path, bytes):
            hid_path = hid_path.decode("utf-8", errors="strict")
        path = str(hid_path)
        prefix = path.split("#{", 1)[0]
        if not prefix.upper().startswith("\\\\?\\HID#"):
            raise ValueError(f"无法识别 Windows HID 路径：{path}")
        return (
            f"{prefix}#{{{WINDOWS_POS_INTERFACE_GUID}}}"
            "\\POSBarcodeScanner"
        )

    @staticmethod
    def _normalize_serial(value) -> str:
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        return str(value or "").strip().upper()

    @staticmethod
    def _side_label(side: str) -> str:
        return {"left": "左侧", "right": "右侧", "enumerate": ""}.get(
            side, f"{side} "
        )
