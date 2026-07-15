"""GPS 串口后台接收器。"""

import os
import threading
import time
from typing import Callable, Iterable, Optional

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None

from .gps_protocol import (
    GpsChecksumError,
    GpsFix,
    GpsLineBuffer,
    GpsProtocolError,
    GpsSnapshot,
    great_circle_distance_m,
    parse_gps_sentence,
)


class GpsSerialReceiver:
    """后台读取 GPS 串口并维护最新线程安全快照。"""

    def __init__(
        self,
        port: str = "",
        baudrate: int = 9600,
        read_timeout: float = 0.2,
        stale_timeout: float = 1.0,
        reconnect_interval: float = 2.0,
        max_buffer_bytes: int = 4096,
        auto_detect: bool = True,
        probe_timeout: float = 1.5,
        excluded_ports: Optional[Iterable[str]] = None,
        serial_factory: Optional[Callable] = None,
        port_provider: Optional[Callable[[], Iterable]] = None,
        clock_ms: Optional[Callable[[], int]] = None,
        speed_min_interval: float = 1.0,
        speed_max_interval: float = 5.0,
        speed_min_distance: float = 0.3,
        speed_max_mps: float = 8.0,
        speed_smoothing_alpha: float = 0.35,
    ):
        self.port = str(port or "").strip()
        self.baudrate = int(baudrate)
        if self.baudrate <= 0:
            raise ValueError("GPS 串口波特率必须大于 0")
        self.read_timeout = max(0.01, float(read_timeout))
        self.stale_timeout_ms = max(1, int(float(stale_timeout) * 1000))
        self.reconnect_interval = max(0.01, float(reconnect_interval))
        self.max_buffer_bytes = max(128, int(max_buffer_bytes))
        self.auto_detect = bool(auto_detect)
        self.probe_timeout = max(self.read_timeout, float(probe_timeout))
        self.speed_min_interval = max(0.1, float(speed_min_interval))
        self.speed_max_interval = max(
            self.speed_min_interval, float(speed_max_interval)
        )
        self.speed_min_distance = max(0.0, float(speed_min_distance))
        self.speed_max_mps = max(0.1, float(speed_max_mps))
        self.speed_smoothing_alpha = min(
            1.0, max(0.01, float(speed_smoothing_alpha))
        )
        self.excluded_ports = {
            self._normalize_port_name(value)
            for value in (excluded_ports or [])
            if str(value or "").strip()
        }
        if not self.port and not self.auto_detect:
            raise ValueError("关闭自动查找时必须配置 GPS 串口")
        if serial_factory is None and serial is None:
            raise RuntimeError("GPS 串口接收需要安装 pyserial>=3.5")
        self.serial_factory = serial_factory or serial.Serial
        if port_provider is not None:
            self.port_provider = port_provider
        elif list_ports is not None:
            self.port_provider = list_ports.comports
        else:
            self.port_provider = lambda: []
        self.clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None
        self._serial = None
        self._active_port = None
        self._has_connected_once = False
        self._latest_fix: Optional[GpsFix] = None
        self._speed_anchor_fix: Optional[GpsFix] = None
        self._latest_speed_mps: Optional[float] = None
        self._last_error_log_at = 0.0
        self._stats = {
            "valid_packets": 0,
            "protocol_errors": 0,
            "checksum_errors": 0,
            "buffer_overflows": 0,
            "connect_failures": 0,
            "read_failures": 0,
            "reconnects": 0,
            "scan_cycles": 0,
            "probe_failures": 0,
            "speed_samples": 0,
            "speed_rejections": 0,
        }

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def active_port(self) -> Optional[str]:
        with self._lock:
            return self._active_port

    def start(self):
        """启动后台接收线程；重复调用不会创建多个线程。"""
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="gps-serial-receiver",
            daemon=True,
        )
        self._thread.start()

    def stop(self, join_timeout: float = 2.0):
        """停止接收并关闭串口，允许后续再次启动。"""
        self._stop_event.set()
        self._close_serial()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=max(0.1, float(join_timeout)))
        self._thread = None

    def get_snapshot(self, now_ms: Optional[int] = None) -> GpsSnapshot:
        """返回最新 GPS 的不可变快照。"""
        with self._lock:
            latest = self._latest_fix
            speed_mps = self._latest_speed_mps
        if latest is None:
            return GpsSnapshot.empty()

        current_ms = int(self.clock_ms() if now_ms is None else now_ms)
        age_ms = max(0, current_ms - latest.received_at_ms)
        stale = age_ms > self.stale_timeout_ms
        return GpsSnapshot(
            fix=latest,
            age_ms=age_ms,
            stale=stale,
            valid=latest.position_valid and not stale,
            speed_mps=(
                speed_mps if latest.position_valid and not stale else None
            ),
        )

    def get_stats(self) -> dict:
        with self._lock:
            return dict(self._stats)

    def _run(self):
        while not self._stop_event.is_set():
            candidates = self._candidate_ports()
            self._increment_stat("scan_cycles")
            if not candidates:
                self._log_error_limited(
                    "未发现可用串口；Ubuntu 请检查设备连接和 dialout 组权限"
                )

            for candidate in candidates:
                if self._stop_event.is_set():
                    break
                try:
                    connection = self._open_serial(candidate)
                    self._serial = connection
                    detected = self._read_loop(
                        connection,
                        port=candidate,
                        require_valid_packet=self.auto_detect,
                    )
                    if self.auto_detect and not detected and not self._stop_event.is_set():
                        self._increment_stat("probe_failures")
                except Exception as exc:
                    if not self._stop_event.is_set():
                        stat_name = "connect_failures" if self._serial is None else "read_failures"
                        self._increment_stat(stat_name)
                        self._log_error_limited(self._format_serial_error(candidate, exc))
                finally:
                    self._close_serial()

            if self._stop_event.wait(self.reconnect_interval):
                break

    def _open_serial(self, port):
        return self.serial_factory(
            port=port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS if serial is not None else 8,
            parity=serial.PARITY_NONE if serial is not None else "N",
            stopbits=serial.STOPBITS_ONE if serial is not None else 1,
            timeout=self.read_timeout,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )

    def _candidate_ports(self):
        candidates = []
        if self.port and self.port.upper() != "AUTO":
            candidates.append(self.port)

        if self.auto_detect:
            try:
                discovered = self.port_provider() or []
            except Exception as exc:
                self._log_error_limited(f"枚举串口失败: {exc}")
                discovered = []
            for item in discovered:
                device = str(getattr(item, "device", item) or "").strip()
                if device:
                    candidates.append(device)

        result = []
        seen = set()
        for candidate in candidates:
            normalized = self._normalize_port_name(candidate)
            if normalized in seen or normalized in self.excluded_ports:
                continue
            seen.add(normalized)
            result.append(candidate)
        return result

    def _read_loop(self, connection, port: str, require_valid_packet: bool):
        line_buffer = GpsLineBuffer(self.max_buffer_bytes)
        previous_overflows = 0
        detected = not require_valid_packet
        probe_deadline = time.monotonic() + self.probe_timeout
        if detected:
            self._activate_port(port)

        while not self._stop_event.is_set():
            waiting = int(getattr(connection, "in_waiting", 0) or 0)
            chunk = connection.read(max(1, min(waiting, 512)))
            if chunk:
                lines = line_buffer.feed(chunk)
                if line_buffer.overflow_count > previous_overflows:
                    difference = line_buffer.overflow_count - previous_overflows
                    self._increment_stat("buffer_overflows", difference)
                    previous_overflows = line_buffer.overflow_count

                for line in lines:
                    if self._handle_line(line) and not detected:
                        detected = True
                        self._activate_port(port)

            if require_valid_packet and not detected and time.monotonic() >= probe_deadline:
                return False
        return detected

    def _handle_line(self, line: bytes):
        try:
            fix = parse_gps_sentence(line, received_at_ms=self.clock_ms())
        except GpsChecksumError as exc:
            self._increment_stat("checksum_errors")
            self._log_error_limited(f"GPS 校验失败: {exc}")
            return False
        except GpsProtocolError as exc:
            self._increment_stat("protocol_errors")
            self._log_error_limited(f"GPS 报文无效: {exc}")
            return False

        with self._lock:
            self._update_speed_locked(fix)
            self._latest_fix = fix
            self._stats["valid_packets"] += 1
        return True

    def _update_speed_locked(self, fix: GpsFix):
        if not fix.position_valid:
            self._speed_anchor_fix = None
            self._latest_speed_mps = None
            return

        previous = self._speed_anchor_fix
        if previous is None:
            self._speed_anchor_fix = fix
            return

        elapsed_s = (fix.received_at_ms - previous.received_at_ms) / 1000.0
        if elapsed_s <= 0:
            self._stats["speed_rejections"] += 1
            return
        if elapsed_s < self.speed_min_interval:
            return

        if elapsed_s > self.speed_max_interval:
            self._speed_anchor_fix = fix
            self._latest_speed_mps = None
            self._stats["speed_rejections"] += 1
            return

        distance_m = great_circle_distance_m(
            previous.latitude,
            previous.longitude,
            fix.latitude,
            fix.longitude,
        )
        raw_speed_mps = (
            0.0 if distance_m < self.speed_min_distance else distance_m / elapsed_s
        )
        if raw_speed_mps > self.speed_max_mps:
            self._latest_speed_mps = None
            self._stats["speed_rejections"] += 1
            return

        self._speed_anchor_fix = fix
        if self._latest_speed_mps is None:
            self._latest_speed_mps = raw_speed_mps
        else:
            alpha = self.speed_smoothing_alpha
            self._latest_speed_mps = (
                alpha * raw_speed_mps + (1.0 - alpha) * self._latest_speed_mps
            )
        self._stats["speed_samples"] += 1

    def _activate_port(self, port: str):
        with self._lock:
            if self._has_connected_once:
                self._stats["reconnects"] += 1
            self._has_connected_once = True
            self._active_port = port
        print(f"[GPS] 已识别串口: {port} @ {self.baudrate}")

    def _close_serial(self):
        connection = self._serial
        self._serial = None
        with self._lock:
            self._active_port = None
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass

    def _increment_stat(self, name: str, amount: int = 1):
        with self._lock:
            self._stats[name] += amount

    def _log_error_limited(self, message: str):
        now = time.monotonic()
        if now - self._last_error_log_at >= 5.0:
            print(f"[GPS] {message}")
            self._last_error_log_at = now

    @staticmethod
    def _normalize_port_name(port: str) -> str:
        value = str(port or "").strip()
        return value if os.name != "nt" else value.lower()

    @staticmethod
    def _format_serial_error(port: str, error: Exception) -> str:
        message = f"串口 {port} 异常: {error}"
        if isinstance(error, PermissionError) or "permission denied" in str(error).lower():
            message += "；Ubuntu 请执行 sudo usermod -aG dialout $USER 后重新登录"
        return message
