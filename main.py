import os
import sys

# 按操作系统选择 Qt 平台插件：Ubuntu/Linux 使用 xcb，Windows 使用 windows
if sys.platform.startswith("linux"):
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
elif sys.platform.startswith("win"):
    os.environ.setdefault("QT_QPA_PLATFORM", "windows")

import time
import argparse
import numpy as np
import torch
import torch.backends.cudnn as cudnn
import cv2
from PIL import Image, ImageDraw, ImageFont
import warnings
from pathlib import Path

from config.app_config import ACTIVE_PRESET, PRESET_NAMES, build_config
from transport.data_mode import (
    DATA_MODES,
    empty_status_data,
    get_data_mode_policy,
    map_common_status_to_udp,
    merge_status_data,
    missing_udp_telemetry_fields,
    select_gps_dms,
)
from transport.stream_resolution import (
    COMMON_STREAM_RESOLUTIONS,
    normalize_resolution_key,
    resize_frame_for_stream,
    resolution_label,
    resolve_stream_size,
)

CONFIG = build_config()

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QMenu, QAction, QListWidgetItem,
    QLabel, QVBoxLayout, QWidget, QSizePolicy, QStyleFactory, QGridLayout,
    QFrame, QHBoxLayout, QPushButton, QScrollArea, QComboBox,
)
from PyQt5.QtCore import Qt, QPoint, QTimer, QThread, pyqtSignal, QCoreApplication
from PyQt5.QtGui import QImage, QPixmap, QIcon, QFont

from main_win.win import Ui_mainWindow
from main_win.realtime_panel import EMPTY_VALUE, build_realtime_view
from main_win.video_recorder import VideoRecorder
from models.experimental import attempt_load
from utils.datasets import LoadImages, LoadWebcam
from utils.CustomMessageBox import MessageBox
from utils.general import check_img_size, check_imshow, non_max_suppression, scale_coords
from utils.plots import colors
from utils.torch_utils import select_device
from utils.capnums import Camera
from dialog.rtsp_win import Window

try:
    from transport.serial_sender import SerialSender
except ImportError as e:
    print(f"⚠️ SerialSender 模块未找到: {e}")
    SerialSender = None

try:
    from transport.http_sender import HttpSender
except ImportError as e:
    print(f"⚠️ HttpSender 模块未找到: {e}")
    HttpSender = None

try:
    from transport.rtmp_sender import RtmpSender
except ImportError as e:
    print(f"⚠️ RtmpSender 模块未找到: {e}")
    RtmpSender = None

try:
    from transport.udp_sender import UdpSender
except ImportError as e:
    print(f"⚠️ UdpSender 模块未找到: {e}")
    UdpSender = None

try:
    from transport.patrol_timeline import PatrolTreeTimeline
except ImportError as e:
    print(f"⚠️ PatrolTreeTimeline 模块未找到: {e}")
    PatrolTreeTimeline = None

try:
    from transport.virtual_sensor import VirtualSensorSimulator
except ImportError as e:
    print(f"⚠️ VirtualSensorSimulator 模块未找到: {e}")
    VirtualSensorSimulator = None

try:
    from transport.gps_protocol import GpsSnapshot
    from transport.gps_serial_receiver import GpsSerialReceiver
    from transport.gps_event_logger import GpsEventLogger
except ImportError as e:
    print(f"⚠️ GPS 串口模块未找到: {e}")
    GpsSnapshot = None
    GpsSerialReceiver = None
    GpsEventLogger = None

try:
    from transport.telemetry_protocol import FLAG_FAULT, TelemetrySnapshot
    from transport.telemetry_serial_receiver import TelemetrySerialReceiver
except ImportError as e:
    print(f"⚠️ 电控遥测串口模块未找到: {e}")
    FLAG_FAULT = 0x0200
    TelemetrySnapshot = None
    TelemetrySerialReceiver = None

warnings.filterwarnings('ignore')

# 字体配置
FONT_SIZE = 20
FONT_PATHS = [
    "simhei.ttf",  # Windows
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",  # Linux
    "/System/Library/Fonts/PingFang.ttc",  # macOS
]

def load_chinese_font(size=FONT_SIZE):
    """加载中文字体，失败时返回默认字体"""
    for font_path in FONT_PATHS:
        try:
            return ImageFont.truetype(font_path, size, encoding="utf-8")
        except (OSError, IOError):
            continue
    return ImageFont.load_default()

# 中文检测框支持
def plot_one_box_chinese(x, im, label=None, color=(128, 128, 128), line_thickness=3):
    im_pil = Image.fromarray(cv2.cvtColor(im, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(im_pil)
    img_width, img_height = im_pil.size
    font = load_chinese_font()
                
    c1, c2 = (int(x[0]), int(x[1])), (int(x[2]), int(x[3]))
    c1 = (max(0, c1[0]), max(0, c1[1]))
    c2 = (min(img_width, c2[0]), min(img_height, c2[1]))
    draw.rectangle([c1, c2], outline=tuple(color), width=line_thickness)

    if label:
        label_size = draw.textbbox((0, 0), label, font=font)[2:]
        label_x1, label_y1 = c1[0], c1[1] - label_size[1] - 3
        label_x2, label_y2 = c1[0] + label_size[0], c1[1]
        if label_y1 < 0:
            label_y1, label_y2 = c1[1], c1[1] + label_size[1] + 3
        label_x1 = max(0, label_x1)
        label_x2 = min(img_width, label_x2)
        label_y1 = max(0, label_y1)
        label_y2 = min(img_height, label_y2)
        draw.rectangle([(label_x1, label_y1), (label_x2, label_y2)], fill=tuple(color))
        text_y = label_y1 + (label_y2 - label_y1 - label_size[1]) // 2
        draw.text((label_x1, text_y), label, fill=(255, 255, 255), font=font)
    return cv2.cvtColor(np.array(im_pil), cv2.COLOR_RGB2BGR)


class LoadRawFrames:
    """只读取原始帧，不做YOLO预处理，用于甲方B纯推流模式。"""

    def __init__(self, source, loop=False, pingpong=False, target_fps=0):
        self.source = source
        self.is_camera = source.isnumeric()
        self.loop = loop and not self.is_camera
        self.pingpong = bool(pingpong and self.loop)
        self.playback_direction = 1
        self.traversal_index = 0
        self.reverse_frame_index = None
        self.target_fps = float(target_fps or 0)
        pipe = int(source) if self.is_camera else source
        if self.is_camera and sys.platform.startswith('win'):
            self.cap = cv2.VideoCapture(pipe, cv2.CAP_DSHOW)
            if not self.cap.isOpened():
                self.cap = cv2.VideoCapture(pipe)
        elif self.is_camera and sys.platform.startswith('linux'):
            self.cap = cv2.VideoCapture(pipe, cv2.CAP_V4L2)
            if not self.cap.isOpened():
                self.cap = cv2.VideoCapture(pipe)
        else:
            self.cap = cv2.VideoCapture(pipe)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 3)
        self.count = 0
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 25
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        self.last_frame_index = max(0, self.frame_count - 1)
        if self.target_fps > 0 and self.fps > self.target_fps:
            self.frame_step = max(1, round(self.fps / self.target_fps))
        else:
            self.frame_step = 1
        self.current_source_time = 0.0

    def __iter__(self):
        return self

    def __next__(self):
        if self.pingpong and self.playback_direction < 0:
            ret, frame = self._read_reverse_frame()
        else:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                if self.pingpong:
                    ret, frame = self._switch_direction_and_read()
                elif self.loop:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    self.playback_direction = 1
                    self.traversal_index += 1
                    ret, frame = self.cap.read()
        if not ret or frame is None:
            self.cap.release()
            raise StopIteration
        pos_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES) or 1) - 1
        if self.playback_direction < 0:
            source_frame_index = max(0, min(self.last_frame_index, pos_frame))
        else:
            source_frame_index = max(0, pos_frame)
            self._skip_forward_frames()
        self.current_source_time = source_frame_index / max(float(self.fps), 1.0)
        self.count += 1
        if self.is_camera:
            frame = cv2.flip(frame, 1)
            path = 'webcam.jpg'
        else:
            path = self.source
        return path, None, frame, self.cap

    def _switch_direction_and_read(self):
        """视频播完后在正放和倒放之间切换，程序不退出。"""
        if self.frame_count <= 1:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            return self.cap.read()

        self.playback_direction *= -1
        self.traversal_index += 1
        if self.playback_direction < 0:
            self.reverse_frame_index = self.last_frame_index
            return self._read_reverse_frame()

        self.reverse_frame_index = None
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        return self.cap.read()

    def _read_reverse_frame(self):
        """从尾到头读取单帧，形成真正的倒放。"""
        if self.reverse_frame_index is None:
            self.reverse_frame_index = self.last_frame_index
        if self.reverse_frame_index < 0:
            return self._switch_direction_and_read()

        self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.reverse_frame_index)
        ret, frame = self.cap.read()
        self.reverse_frame_index -= self.frame_step
        return ret, frame

    def _skip_forward_frames(self):
        """按目标输出帧率跳过若干原视频帧，保持原视频时间轴不变。"""
        if self.frame_step <= 1 or self.is_camera:
            return
        next_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES) or 0) + self.frame_step - 1
        if self.frame_count > 0:
            next_frame = min(next_frame, self.frame_count)
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, next_frame)


class DetThread(QThread):
    send_img = pyqtSignal(np.ndarray)
    send_raw = pyqtSignal(np.ndarray)
    send_statistic = pyqtSignal(dict)
    send_data = pyqtSignal(dict)
    send_msg = pyqtSignal(str)
    send_percent = pyqtSignal(int)
    send_fps = pyqtSignal(str)

    def __init__(self, config=None):
        super(DetThread, self).__init__()
        
        # 使用传入的配置，如果没有则使用全局默认 CONFIG
        self.cfg = config if config else CONFIG
        self.data_policy = get_data_mode_policy(self.cfg.get("DATA_MODE"))
        self.cfg["DATA_MODE"] = self.data_policy.name
        
        self.weights = self.cfg["WEIGHTS"]
        self.current_weight = self.cfg["WEIGHTS"]
        self.source = self.cfg["SOURCE"]
        self.conf_thres = self.cfg["CONF_THRES"]
        self.iou_thres = self.cfg["IOU_THRES"]
        
        self.jump_out = False
        self.is_continue = True
        self.percent_length = 1000
        self.rate_check = True
        # PARAM
        self.rate = float(self.cfg.get("PLAYBACK_RATE_FPS") or 100)
        self.save_fold = './result'

        self.serial_sender = None
        self.http_sender = None
        self.rtmp_sender = None
        self.udp_sender = None
        self.telemetry_receiver = None
        self.gps_receiver = None
        self.gps_event_logger = None
        self.dataset = None
        self.vid_cap = None
        needs_virtual_sensor = (
            self.data_policy.use_virtual_status
            or self.data_policy.use_virtual_gps
        )
        if needs_virtual_sensor and VirtualSensorSimulator:
            self.sensor_sim = VirtualSensorSimulator(
                lat_decimal=self.cfg.get("SIM_BASE_LAT"),
                lon_decimal=self.cfg.get("SIM_BASE_LON"),
                use_system_location=(
                    self.cfg.get("USE_SYSTEM_LOCATION", False)
                    and not self.data_policy.force_virtual
                ),
            )
        else:
            self.sensor_sim = None

        # --- HTTP 上报频率控制 ---
        # PARAM
        self.last_http_send_time = 0  # 记录上次发送的时间戳
        self.http_send_interval = 2.0 # 最小发送间隔（秒），可根据需要调整为 1.0, 5.0 等

        # --- UDP 上报频率控制 ---
        self.last_udp_send_time = 0
        self.udp_send_interval = 1.0  # UDP 发送间隔（秒）
        self.udp_send_count = 0
        self.last_missing_telemetry_log_time = 0
        self.last_real_tree_state = None
        self.patrol_timeline = self._build_patrol_timeline()
        # -----------------------------

        # 1. 初始化串口
        if self.cfg["ENABLE_SERIAL"] and SerialSender is not None:
            try:
                self.serial_sender = SerialSender(port=self.cfg["SERIAL_PORT"], baudrate=self.cfg["BAUDRATE"])
                if not self.serial_sender.open_serial():
                    self.serial_sender = None
            except Exception as e:
                print(f"❌ 串口打开失败: {e.__class__.__name__}: {e}")
                self.serial_sender = None

        # 统一电控遥测是正式真实数据入口，仿真模式完全不打开硬件串口
        if self.data_policy.use_real_telemetry and self.cfg.get("ENABLE_TELEMETRY_SERIAL"):
            telemetry_port = str(self.cfg.get("TELEMETRY_SERIAL_PORT", "")).strip()
            auto_detect = bool(self.cfg.get("TELEMETRY_SERIAL_AUTO_DETECT", True))
            disease_port = str(getattr(self.serial_sender, "port", "") or "").strip()
            ports_conflict = (
                self.serial_sender is not None
                and telemetry_port
                and disease_port
                and telemetry_port.lower() == disease_port.lower()
            )
            if ports_conflict:
                print(f"❌ 遥测串口与病害发送串口冲突: {telemetry_port}")
            elif not telemetry_port and not auto_detect:
                print("❌ 遥测串口未配置，无法启动接收器")
            elif TelemetrySerialReceiver is None:
                print("❌ 电控遥测串口模块未加载，请确认已经安装 pyserial")
            else:
                try:
                    self.telemetry_receiver = TelemetrySerialReceiver(
                        port=telemetry_port,
                        baudrate=self.cfg.get("TELEMETRY_SERIAL_BAUDRATE", 9600),
                        read_timeout=self.cfg.get("TELEMETRY_SERIAL_READ_TIMEOUT", 0.2),
                        stale_timeout=self.cfg.get("TELEMETRY_STALE_TIMEOUT", 1.0),
                        reconnect_interval=self.cfg.get("TELEMETRY_RECONNECT_INTERVAL", 2.0),
                        max_buffer_bytes=self.cfg.get("TELEMETRY_MAX_BUFFER_BYTES", 4096),
                        auto_detect=auto_detect,
                        probe_timeout=self.cfg.get("TELEMETRY_SERIAL_PROBE_TIMEOUT", 1.5),
                        excluded_ports=[disease_port] if disease_port else [],
                        speed_min_interval=self.cfg.get("GPS_SPEED_MIN_INTERVAL", 1.0),
                        speed_max_interval=self.cfg.get("GPS_SPEED_MAX_INTERVAL", 5.0),
                        speed_min_distance=self.cfg.get("GPS_SPEED_MIN_DISTANCE", 0.3),
                        speed_max_mps=self.cfg.get("GPS_SPEED_MAX_MPS", 8.0),
                        speed_smoothing_alpha=self.cfg.get(
                            "GPS_SPEED_SMOOTHING_ALPHA", 0.35
                        ),
                    )
                except Exception as e:
                    print(f"❌ 电控遥测串口接收器初始化失败: {e}")
                    self.telemetry_receiver = None
        elif self.cfg.get("ENABLE_TELEMETRY_SERIAL"):
            print("ℹ️ 仿真模式：忽略电控遥测串口配置")

        # 旧 OPGPS 接收保留兼容，并与统一遥测串口相互独立
        if self.data_policy.use_serial_gps and self.cfg.get("ENABLE_GPS_SERIAL"):
            gps_port = str(self.cfg.get("GPS_SERIAL_PORT", "")).strip()
            disease_port = str(
                getattr(self.serial_sender, "port", "") or ""
            ).strip()
            telemetry_port = str(
                getattr(self.telemetry_receiver, "port", "") or ""
            ).strip()
            auto_detect = bool(self.cfg.get("GPS_SERIAL_AUTO_DETECT", True))
            ports_conflict = (
                self.serial_sender is not None
                and gps_port
                and disease_port
                and gps_port.lower() == disease_port.lower()
            )
            if ports_conflict:
                print(f"❌ GPS 串口与病害发送串口冲突: {gps_port}")
            elif not gps_port and not auto_detect:
                print("❌ GPS 串口未配置，无法启动接收器")
            elif GpsSerialReceiver is None:
                print("❌ GPS 串口模块未加载，请确认已经安装 pyserial")
            else:
                try:
                    self.gps_receiver = GpsSerialReceiver(
                        port=gps_port,
                        baudrate=self.cfg.get("GPS_SERIAL_BAUDRATE", 9600),
                        read_timeout=self.cfg.get("GPS_SERIAL_READ_TIMEOUT", 0.2),
                        stale_timeout=self.cfg.get("GPS_STALE_TIMEOUT", 1.0),
                        reconnect_interval=self.cfg.get("GPS_RECONNECT_INTERVAL", 2.0),
                        max_buffer_bytes=self.cfg.get("GPS_MAX_BUFFER_BYTES", 4096),
                        auto_detect=auto_detect,
                        probe_timeout=self.cfg.get("GPS_SERIAL_PROBE_TIMEOUT", 1.5),
                        excluded_ports=[
                            port for port in (disease_port, telemetry_port) if port
                        ],
                        speed_min_interval=self.cfg.get("GPS_SPEED_MIN_INTERVAL", 1.0),
                        speed_max_interval=self.cfg.get("GPS_SPEED_MAX_INTERVAL", 5.0),
                        speed_min_distance=self.cfg.get("GPS_SPEED_MIN_DISTANCE", 0.3),
                        speed_max_mps=self.cfg.get("GPS_SPEED_MAX_MPS", 8.0),
                        speed_smoothing_alpha=self.cfg.get(
                            "GPS_SPEED_SMOOTHING_ALPHA", 0.35
                        ),
                    )
                    if GpsEventLogger is not None:
                        self.gps_event_logger = GpsEventLogger(
                            log_dir=self.cfg.get("GPS_EVENT_LOG_DIR", "./result/gps_events"),
                            retention_days=self.cfg.get("GPS_EVENT_LOG_RETENTION_DAYS", 3),
                        )
                except Exception as e:
                    print(f"❌ GPS 串口接收器初始化失败: {e}")
                    self.gps_receiver = None
        elif self.cfg.get("ENABLE_GPS_SERIAL") and self.data_policy.use_virtual_gps:
            print("ℹ️ 仿真模式：忽略 GPS 串口配置，位置使用虚拟数据")

        # 2. 初始化 HTTP
        if self.cfg["ENABLE_HTTP"] and HttpSender is not None:
            if self.cfg["HTTP_URL"]:
                self.http_sender = HttpSender(push_url=self.cfg["HTTP_URL"])
                self.http_sender.start_server()
            else:
                print("⚠️ HTTP URL 为空，跳过初始化")

        # 3. 初始化 RTMP
        if self.cfg["ENABLE_RTMP"] and RtmpSender is not None:
            if self.cfg["RTMP_URL"]:
                self.rtmp_sender = RtmpSender(
                    rtmp_url=self.cfg["RTMP_URL"],
                    video_bitrate=self.cfg.get("RTMP_VIDEO_BITRATE", "1200k"),
                    maxrate=self.cfg.get("RTMP_MAXRATE", "1500k"),
                    bufsize=self.cfg.get("RTMP_BUFSIZE", "2400k"),
                    overlay_timestamp=self.cfg.get("RTMP_TIMESTAMP_OVERLAY", False),
                    time_standard=self.cfg.get("RTMP_TIME_STANDARD", "local"),
                )
            else:
                print("⚠️ RTMP URL 为空，跳过初始化")

        # 4. 初始化 UDP
        if self.cfg.get("ENABLE_UDP"):
            print(f"🔍 UDP 配置检查:")
            print(f"   ENABLE_UDP: {self.cfg.get('ENABLE_UDP')}")
            print(f"   UDP_HOST: {self.cfg.get('UDP_HOST')}")
            print(f"   UDP_PORT: {self.cfg.get('UDP_PORT')}")
            print(f"   UdpSender 模块: {'已加载' if UdpSender is not None else '未加载'}")

            if UdpSender is None:
                print("❌ UdpSender 模块未加载，无法初始化 UDP")
            elif self.cfg.get("UDP_HOST") and self.cfg.get("UDP_PORT"):
                try:
                    print(f"🔧 正在初始化 UDP 发送器...")
                    self.udp_sender = UdpSender(
                        udp_host=self.cfg["UDP_HOST"],
                        udp_port=self.cfg["UDP_PORT"],
                        robot_id=self.cfg.get("ROBOT_ID", 1),
                        sensor_id=self.cfg.get("SENSOR_ID", 1),
                        orchard_id=self.cfg.get("UDP_ORCHARD_ID", "orchard1"),
                        add_orchard_prefix=self.cfg.get("UDP_ADD_ORCHARD_PREFIX", False),
                        simulate_tree_events=(
                            self.data_policy.use_virtual_events
                            and self.cfg.get("SIMULATE_TREE_EVENTS", False)
                        ),
                        tree_interval=self.cfg.get("TREE_INTERVAL", 8),
                        tree_jitter=self.cfg.get("TREE_JITTER", 2),
                        tree_hold_frames=self.cfg.get("TREE_HOLD_FRAMES", 5),
                        time_standard=self.cfg.get("UDP_TIME_STANDARD", "local"),
                    )
                    print(f"✅ UDP 发送器已初始化: {self.cfg['UDP_HOST']}:{self.cfg['UDP_PORT']}")
                    print(f"   Robot ID: {self.cfg.get('ROBOT_ID', 1)}")
                    print(f"   Sensor ID: {self.cfg.get('SENSOR_ID', 1)}")
                except Exception as e:
                    print(f"❌ UDP 初始化失败: {e.__class__.__name__}: {e}")
                    import traceback
                    traceback.print_exc()
                    self.udp_sender = None
            else:
                print("⚠️ UDP HOST/PORT 为空，跳过初始化")
        else:
            print("ℹ️ UDP 未启用（ENABLE_UDP=False）")

    def _build_patrol_timeline(self):
        """只为甲方B UDP 演示视频启用固定巡检时间轴。"""
        if not self.data_policy.use_virtual_events:
            return None
        if not self.cfg.get("ENABLE_UDP") or not self.cfg.get("ENABLE_PATROL_TIMELINE"):
            return None
        if PatrolTreeTimeline is None:
            return None

        source_name = Path(str(self.source)).name.lower()
        expected_name = str(self.cfg.get("PATROL_SOURCE_NAME", "")).lower()
        if expected_name and source_name != expected_name:
            return None

        event_times = self.cfg.get("PATROL_TREE_TIMES", [])
        if not event_times:
            return None

        timeline = PatrolTreeTimeline(
            event_times=event_times,
            start_tree_id=self.cfg.get("PATROL_START_TREE_ID", 1),
        )
        print(f"✅ 甲方B UDP 固定巡检时间轴已启用: {source_name}")
        print(f"   果树编号从 ID{int(self.cfg.get('PATROL_START_TREE_ID', 1)):04d} 开始")
        if self.cfg.get("PATROL_TIMELINE_DEBUG", False):
            print(f"   调试秒点: {event_times}")
        return timeline

    def _start_data_receivers(self):
        """按需启动真实遥测和旧 GPS 接收线程。"""
        if self.telemetry_receiver and not self.telemetry_receiver.is_running:
            self.telemetry_receiver.start()
        if self.gps_receiver and not self.gps_receiver.is_running:
            self.gps_receiver.start()

    def _get_frame_telemetry_snapshot(self):
        """每个处理帧只读取一次统一电控遥测。"""
        if self.data_policy.use_real_telemetry and self.cfg.get("ENABLE_TELEMETRY_SERIAL"):
            if self.telemetry_receiver:
                return self.telemetry_receiver.get_snapshot()
            return TelemetrySnapshot.empty() if TelemetrySnapshot is not None else None
        return None

    def _get_frame_gps_snapshot(self):
        """读取旧 OPGPS 快照，作为统一遥测 GPS 的兼容回退。"""
        if self.data_policy.use_serial_gps and self.cfg.get("ENABLE_GPS_SERIAL"):
            if self.gps_receiver:
                return self.gps_receiver.get_snapshot()
            return GpsSnapshot.empty() if GpsSnapshot is not None else None
        return None

    @staticmethod
    def _select_real_gps_snapshot(telemetry_snapshot, legacy_gps_snapshot):
        """统一遥测 GPS 优先，无有效定位时回退旧 OPGPS。"""
        if (
            telemetry_snapshot is not None
            and getattr(telemetry_snapshot, "valid", False)
            and telemetry_snapshot.to_dms() is not None
        ):
            return telemetry_snapshot
        if legacy_gps_snapshot is not None and getattr(legacy_gps_snapshot, "valid", False):
            return legacy_gps_snapshot
        return telemetry_snapshot or legacy_gps_snapshot

    def _get_frame_gps_dms(self, gps_snapshot):
        virtual_gps_dms = None
        if self.sensor_sim and self.data_policy.use_virtual_gps:
            virtual_gps_dms = self.sensor_sim.get_gps_dms()
        return select_gps_dms(
            policy=self.data_policy,
            gps_snapshot=gps_snapshot,
            virtual_gps_dms=virtual_gps_dms,
        )

    def _log_missing_udp_telemetry(self, missing_fields, now):
        if now - self.last_missing_telemetry_log_time < 5.0:
            return
        print(
            "⚠️ UDP 未发送：真实遥测缺失 "
            f"({', '.join(missing_fields)})，不会用 0 或虚拟值代替"
        )
        self.last_missing_telemetry_log_time = now

    def _log_gps_event(
        self,
        event_type,
        channel,
        frame_index,
        source_time_s,
        gps_snapshot,
        diseases=None,
        tree_event=None,
    ):
        """记录业务事件；日志故障不能影响检测和平台上报。"""
        if not self.gps_event_logger or gps_snapshot is None:
            return
        try:
            self.gps_event_logger.log_event(
                event_type=event_type,
                channel=channel,
                frame_index=frame_index,
                source_time_s=source_time_s,
                gps_snapshot=gps_snapshot,
                diseases=diseases,
                tree_event=tree_event,
            )
        except Exception as e:
            print(f"⚠️ GPS 事件日志写入失败: {e}")

    def _should_pingpong_source(self):
        """仅对本地演示视频启用正放/倒放循环。"""
        if not self.cfg.get("PINGPONG_SOURCE", False):
            return False
        source = str(self.source)
        if source.isnumeric() or source.lower().startswith(('rtsp://', 'rtmp://', 'http://', 'https://')):
            return False
        expected_name = str(self.cfg.get("PATROL_SOURCE_NAME", "")).lower()
        return not expected_name or Path(source).name.lower() == expected_name

    def cleanup_resources(self, stop_gps=True):
        dataset = getattr(self, "dataset", None)
        if dataset is not None and getattr(dataset, "cap", None) is not None:
            try: dataset.cap.release()
            except: pass
        if getattr(self, "vid_cap", None) is not None:
            try: self.vid_cap.release()
            except: pass
        if stop_gps:
            if self.telemetry_receiver:
                try: self.telemetry_receiver.stop()
                except: pass
            if self.gps_receiver:
                try: self.gps_receiver.stop()
                except: pass
        if self.serial_sender:
            try: self.serial_sender.close_serial()
            except: pass
        if self.http_sender:
            try: self.http_sender.stop()
            except: pass
        if self.rtmp_sender:
            try: self.rtmp_sender.stop()
            except: pass
        if self.udp_sender:
            try: self.udp_sender.close()
            except: pass

    @torch.no_grad()
    def run(self, imgsz=None, max_det=1000, device='', view_img=True, save_txt=False, 
            save_conf=False, save_crop=False, nosave=False, classes=None, agnostic_nms=False, 
            augment=False, visualize=False, update=False, project='runs/detect', name='exp', 
            exist_ok=False, line_thickness=3, hide_labels=False, hide_conf=False, half=False):
        
        if imgsz is None:
            imgsz = self.cfg["IMG_SIZE"]
        raw_stream_only = bool(self.cfg.get("RAW_STREAM_ONLY", False))

        print("="*50)
        print("🚀 检测线程启动")
        print(f"   配置方案: {self.cfg.get('PRESET_NAME', ACTIVE_PRESET)}")
        print(f"   数据模式: {self.data_policy.label} ({self.data_policy.name})")
        print(f"   工作模式: {'原始视频推流' if raw_stream_only else 'YOLO识别'}")
        if not raw_stream_only:
            print(f"   模型: {self.weights}")
        print(f"   源: {self.source}")
        print(
            f"   HTTP: {'✅' if self.http_sender else '❌'} | "
            f"RTMP: {'✅' if self.rtmp_sender else '❌'} | "
            f"UDP: {'✅' if self.udp_sender else '❌'} | "
            f"遥测: {'✅' if self.telemetry_receiver else '❌'} | "
            f"旧GPS: {'✅' if self.gps_receiver else '❌'}"
        )
        if self.data_policy.use_real_telemetry and self.cfg.get("ENABLE_TELEMETRY_SERIAL"):
            print(
                f"   遥测串口: {self.cfg.get('TELEMETRY_SERIAL_PORT') or 'AUTO'} @ "
                f"{self.cfg.get('TELEMETRY_SERIAL_BAUDRATE', 9600)}"
            )
        if self.data_policy.use_serial_gps and self.cfg.get("ENABLE_GPS_SERIAL"):
            print(
                f"   GPS串口: {self.cfg.get('GPS_SERIAL_PORT') or 'AUTO'} @ "
                f"{self.cfg.get('GPS_SERIAL_BAUDRATE', 9600)}"
            )
        print("="*50)
        
        try:
            self._start_data_receivers()
            stride = 32
            model = None
            names = ["溃疡病", "黄龙病", "炭疽病"]

            if not raw_stream_only:
                device = select_device(device)
                half &= device.type != 'cpu'
                model = attempt_load(self.weights, map_location=device)
                stride = int(model.stride.max())
                imgsz = check_img_size(imgsz, s=stride)
                
                names = model.names
                name_mapping = {"Canker": "溃疡病", "Huanglongbing": "黄龙病", "Anthracnose": "炭疽病"}
                names = [name_mapping.get(n, n) for n in names]
                
                if half:
                    model.half()
            else:
                print("ℹ️ 当前为纯推流模式：跳过模型加载、图像预处理、推理和后处理")

            pingpong_source = self._should_pingpong_source()
            raw_frame_target_fps = self.cfg.get("RAW_FRAME_TARGET_FPS", 0)

            if self.source.isnumeric() or self.source.lower().startswith(('rtsp://', 'rtmp://', 'http://', 'https')):
                if raw_stream_only:
                    dataset = LoadRawFrames(
                        self.source,
                        loop=self.cfg.get("LOOP_SOURCE", True),
                        pingpong=pingpong_source,
                        target_fps=raw_frame_target_fps,
                    )
                else:
                    # check_imshow()
                    cudnn.benchmark = True
                    dataset = LoadWebcam(self.source, img_size=imgsz, stride=stride)
            else:
                if raw_stream_only:
                    dataset = LoadRawFrames(
                        self.source,
                        loop=self.cfg.get("LOOP_SOURCE", True),
                        pingpong=pingpong_source,
                        target_fps=raw_frame_target_fps,
                    )
                else:
                    dataset = LoadImages(self.source, img_size=imgsz, stride=stride)

            if pingpong_source:
                print("✅ 本地演示视频已启用正放/倒放循环，程序不会在视频末尾停止")

            if not raw_stream_only and device.type != 'cpu':
                model(torch.zeros(1, 3, imgsz, imgsz).to(device).type_as(next(model.parameters())))

            count = 0
            start_time = time.time()
            self.dataset = dataset
            dataset = iter(dataset)
            rtmp_initialized = False

            while True:
                if self.jump_out:
                    break
                if not self.is_continue:
                    time.sleep(0.01)
                    continue

                try:
                    path, img, im0s, self.vid_cap = next(dataset)
                except StopIteration:
                    break

                # RTMP 初始化
                if self.cfg["ENABLE_RTMP"] and self.rtmp_sender and not rtmp_initialized:
                    h, w = im0s.shape[:2] # <--- 这里获取的是摄像头原始画面的高和宽
                    
                    push_w, push_h = resolve_stream_size(
                        w,
                        h,
                        resolution=self.cfg.get("RTMP_RESOLUTION"),
                        legacy_max_width=self.cfg.get("RTMP_MAX_WIDTH", 1280),
                    )
                    
                    fps = 25
                    if self.vid_cap:
                        fps = int(self.vid_cap.get(cv2.CAP_PROP_FPS)) or 25
                    fps = min(fps, int(self.cfg.get("RTMP_MAX_FPS", fps)))
                    # self.rtmp_sender.start(w, h, fps) # <--- 将原始宽高传给推流器
                    self.rtmp_sender.start(push_w, push_h, fps)
                    print(f"📹 RTMP 推流启动: {push_w}x{push_h} @ {fps}fps")
                    rtmp_initialized = True

                count += 1
                if count % 30 == 0 and count >= 30:
                    fps_val = int(30 / (time.time() - start_time))
                    self.send_fps.emit(f'fps：{fps_val}')
                    start_time = time.time()

                statistic_dic = {n: 0 for n in names}
                max_conf_dic = {n: 0.0 for n in names}
                im0 = im0s.copy()
                render_detection_overlay = (
                    not self.cfg.get("HEADLESS", False)
                    or bool(self.cfg.get("ENABLE_HTTP") and self.http_sender)
                )

                if not raw_stream_only:
                    img = torch.from_numpy(img).to(device)
                    img = img.half() if half else img.float()
                    img /= 255.0
                    if img.ndimension() == 3:
                        img = img.unsqueeze(0)

                    pred = model(img, augment=augment)[0]
                    pred = non_max_suppression(pred, self.conf_thres, self.iou_thres, classes, agnostic_nms, max_det=max_det)

                    for i, det in enumerate(pred):
                        if len(det):
                            det[:, :4] = scale_coords(img.shape[2:], det[:, :4], im0.shape).round()
                            for *xyxy, conf, cls in reversed(det):
                                c = int(cls)
                                class_name = names[c]
                                statistic_dic[class_name] += 1
                                current_conf = float(conf)
                                if current_conf > max_conf_dic[class_name]:
                                    max_conf_dic[class_name] = current_conf
                                label = None if hide_labels else (names[c] if hide_conf else f'{names[c]} {conf:.2f}')
                                if render_detection_overlay:
                                    im0 = plot_one_box_chinese(xyxy, im0, label=label, color=colors(c, True), line_thickness=line_thickness)

                count_canker = statistic_dic.get("溃疡病", 0)
                count_huanglong = statistic_dic.get("黄龙病", 0)
                count_anthrac = statistic_dic.get("炭疽病", 0)
                conf_canker = max_conf_dic.get("溃疡病", 0.0)
                conf_huanglong = max_conf_dic.get("黄龙病", 0.0)
                conf_anthrac = max_conf_dic.get("炭疽病", 0.0)
                disease_count = count_canker + count_huanglong + count_anthrac
                disease_detected = disease_count > 0

                source_time_s = getattr(dataset, "current_source_time", None)
                timeline_tree_event = None
                if self.patrol_timeline:
                    timeline_tree_event = self.patrol_timeline.consume_event(
                        playback_time=source_time_s,
                        playback_direction=getattr(dataset, "playback_direction", 1),
                        traversal_index=getattr(dataset, "traversal_index", 0),
                    )
                    if timeline_tree_event:
                        timeline_tree_event = dict(timeline_tree_event)
                        timeline_tree_event["source"] = "simulation"
                        timeline_tree_event["current_tree_id"] = timeline_tree_event.get(
                            "tree_id", timeline_tree_event.get("left_tree_id", 0)
                        )

                # 每个处理帧只读取一次硬件快照，所有平台和 UI 共用同一份数据
                telemetry_snapshot = self._get_frame_telemetry_snapshot()
                legacy_gps_snapshot = self._get_frame_gps_snapshot()
                frame_gps_snapshot = self._select_real_gps_snapshot(
                    telemetry_snapshot,
                    legacy_gps_snapshot,
                )
                real_tree_data = None
                if (
                    not self.data_policy.force_virtual
                    and telemetry_snapshot is not None
                    and getattr(telemetry_snapshot, "valid", False)
                ):
                    real_tree_data = telemetry_snapshot.to_tree_data()
                tree_event = real_tree_data if real_tree_data is not None else timeline_tree_event
                tree_present = bool(
                    tree_event
                    and (
                        tree_event.get("current_tree_id")
                        or tree_event.get("left_tree_id")
                        or tree_event.get("right_tree_id")
                    )
                )
                tree_state_changed = False
                explicit_tree_indices = None
                if real_tree_data is not None:
                    tree_state = (
                        real_tree_data["current_tree_id"],
                        real_tree_data["left_tree_id"],
                        real_tree_data["right_tree_id"],
                        real_tree_data["camera_side"],
                    )
                    tree_state_changed = tree_state != self.last_real_tree_state
                    self.last_real_tree_state = tree_state
                    explicit_tree_indices = (
                        real_tree_data["left_tree_id"],
                        real_tree_data["right_tree_id"],
                    )

                if self.sensor_sim and (
                    self.data_policy.use_virtual_status
                    or self.data_policy.use_virtual_gps
                ):
                    self.sensor_sim.update(
                        count,
                        is_near_tree=disease_detected or tree_present,
                    )
                virtual_status_data = {}
                if self.sensor_sim and self.data_policy.use_virtual_status:
                    virtual_status_data = self.sensor_sim.get_status_data()
                    virtual_status_data["robot_status"] = 1

                real_status_data = empty_status_data()
                real_status_sources = {}
                if (
                    telemetry_snapshot is not None
                    and getattr(telemetry_snapshot, "valid", False)
                ):
                    telemetry_status = telemetry_snapshot.to_status_data()
                    for field, value in telemetry_status.items():
                        if field in real_status_data and value is not None:
                            real_status_data[field] = value
                            real_status_sources[field] = "real"
                    telemetry_data = telemetry_snapshot.telemetry
                    if (
                        real_status_data.get("velocity") is not None
                        and telemetry_data.actual_velocity_mps is None
                    ):
                        real_status_sources["velocity"] = "estimated"
                    if telemetry_data.has(FLAG_FAULT):
                        real_status_data["fault_code"] = telemetry_data.fault_code
                        real_status_sources["fault_code"] = "real"

                # 旧 OPGPS 仅在统一遥测没有速度时提供估算回退
                if (
                    real_status_data.get("velocity") is None
                    and legacy_gps_snapshot is not None
                    and getattr(legacy_gps_snapshot, "valid", False)
                    and getattr(legacy_gps_snapshot, "speed_mps", None) is not None
                ):
                    real_status_data["velocity"] = legacy_gps_snapshot.speed_mps
                    real_status_sources["velocity"] = "estimated"

                status_data = merge_status_data(
                    policy=self.data_policy,
                    real_status_data=real_status_data,
                    virtual_status_data=virtual_status_data,
                )
                status_sources = {}
                for field, value in status_data.items():
                    if value is None:
                        status_sources[field] = "unavailable"
                    elif field in real_status_sources:
                        status_sources[field] = real_status_sources[field]
                    elif virtual_status_data.get(field) is not None:
                        status_sources[field] = "virtual"
                    else:
                        status_sources[field] = "unknown"

                gps_dms = self._get_frame_gps_dms(frame_gps_snapshot)
                if gps_dms is not None:
                    lat_d, lat_m, lat_s, lat_dir, lon_d, lon_m, lon_s, lon_dir = gps_dms
                else:
                    lat_d = lat_m = lat_s = lat_dir = None
                    lon_d = lon_m = lon_s = lon_dir = None
                diseases_for_log = {
                    "溃疡病": {"count": count_canker, "confidence": conf_canker},
                    "黄龙病": {"count": count_huanglong, "confidence": conf_huanglong},
                    "炭疽病": {"count": count_anthrac, "confidence": conf_anthrac},
                }
                current_time = time.time()
                gps_snapshot_data = (
                    frame_gps_snapshot.to_dict()
                    if frame_gps_snapshot is not None and hasattr(frame_gps_snapshot, "to_dict")
                    else {}
                )
                uses_real_gps = (
                    not self.data_policy.force_virtual
                    and frame_gps_snapshot is not None
                    and getattr(frame_gps_snapshot, "valid", False)
                    and frame_gps_snapshot.to_dms() is not None
                )
                if uses_real_gps and gps_snapshot_data:
                    gps_snapshot_data.update({
                        "source": "serial",
                        "transport": (
                            "telemetry"
                            if frame_gps_snapshot is telemetry_snapshot
                            else "opgps"
                        ),
                        "simulated": False,
                    })
                elif self.data_policy.use_virtual_gps and self.sensor_sim:
                    gps_snapshot_data = {
                        "available": gps_dms is not None,
                        "valid": gps_dms is not None,
                        "stale": False,
                        "latitude": self.sensor_sim.lat_decimal,
                        "longitude": self.sensor_sim.lon_decimal,
                        "source": "virtual",
                        "simulated": True,
                    }
                elif gps_snapshot_data:
                    gps_snapshot_data.update({"source": "serial", "simulated": False})
                battery_sources = {
                    status_sources.get(field, "unavailable")
                    for field in ("soc", "bat_voltage")
                    if status_data.get(field) is not None
                }
                if not battery_sources:
                    battery_source = "unavailable"
                elif "virtual" in battery_sources:
                    battery_source = "virtual"
                elif battery_sources == {"real"}:
                    battery_source = "real"
                else:
                    battery_source = "unknown"
                gps_source = (
                    "real" if uses_real_gps
                    else "virtual" if gps_snapshot_data.get("simulated") is True
                    else "unavailable"
                )
                self.send_data.emit({
                    "frame_index": count,
                    "source_time_s": source_time_s,
                    "work_mode": "原始视频推流" if raw_stream_only else "YOLO识别",
                    "data_mode": self.data_policy.name,
                    "data_mode_label": self.data_policy.label,
                    "disease_count": disease_count,
                    "disease_detected": disease_detected,
                    "diseases": diseases_for_log,
                    "status": status_data,
                    "gps_dms": gps_dms,
                    "gps": gps_snapshot_data,
                    "tree_event": tree_event,
                    "field_sources": {
                        "gps": gps_source,
                        "robot_status": status_sources.get("robot_status", "unavailable"),
                        "velocity": status_sources.get("velocity", "unavailable"),
                        "azimuth": status_sources.get("azimuth", "unavailable"),
                        "camera_height": status_sources.get("eyepoint_height", "unavailable"),
                        "battery": battery_source,
                        "route": (
                            "real"
                            if status_sources.get("route_index") == "real"
                            or status_sources.get("waypoint_index") == "real"
                            else "virtual"
                            if status_sources.get("route_index") == "virtual"
                            or status_sources.get("waypoint_index") == "virtual"
                            else "unavailable"
                        ),
                        "fault": status_sources.get("fault_code", "unavailable"),
                        "tree": (
                            "real" if real_tree_data is not None
                            else "virtual" if timeline_tree_event
                            else "unavailable"
                        ),
                        "work_mode": "real",
                        "frame_index": "real",
                        "disease_count": "real",
                        "channels": "real",
                    },
                    "udp_send_count": self.udp_send_count,
                    "channels": {
                        "HTTP": bool(self.http_sender),
                        "RTMP": bool(self.rtmp_sender),
                        "UDP": bool(self.udp_sender),
                        "遥测": bool(self.telemetry_receiver),
                        "旧GPS": bool(self.gps_receiver),
                    },
                })

                # HTTP 发送数据
                if self.cfg["ENABLE_HTTP"] and self.http_sender:
                    try:
                        should_send = (
                            (disease_detected or count % 500 == 0)
                            and current_time - self.last_http_send_time > self.http_send_interval
                        )
                        if should_send:
                            serial_robot_id = (
                                telemetry_snapshot.telemetry.robot_id
                                if telemetry_snapshot is not None
                                and getattr(telemetry_snapshot, "valid", False)
                                else int(self.cfg.get("ROBOT_ID", 1))
                            )
                            current_tree_id = (
                                tree_event.get(
                                    "current_tree_id",
                                    tree_event.get(
                                        "tree_id", tree_event.get("left_tree_id", 0)
                                    ),
                                )
                                if tree_event
                                else (0 if self.data_policy.use_virtual_events else None)
                            )
                            self.http_sender.send_robot_with_disease(
                                robot_id=f"ROBOT_{serial_robot_id:03d}",
                                robot_status=status_data["robot_status"],
                                frame_index=count,
                                route_index=status_data['route_index'],
                                waypoint_index=status_data['waypoint_index'],
                                tree_index=current_tree_id,
                                lat_degree=lat_d, lat_minute=lat_m, lat_second=lat_s, lat_direction=lat_dir,
                                lon_degree=lon_d, lon_minute=lon_m, lon_second=lon_s, lon_direction=lon_dir,
                                azimuth=status_data['azimuth'],
                                velocity=status_data['velocity'],
                                eyepoint_height=status_data['eyepoint_height'],
                                bat_voltage=status_data['bat_voltage'],
                                state_of_charge=status_data['soc'],
                                conf1=conf_canker, count1=count_canker,
                                conf2=conf_huanglong, count2=count_huanglong,
                                conf3=conf_anthrac, count3=count_anthrac,
                                image_frame=im0,
                            )
                            self.last_http_send_time = current_time
                            print(f"📤 HTTP 上报 | 帧:{count} | 病害:{disease_count}")
                            if disease_detected:
                                self._log_gps_event(
                                    event_type="disease",
                                    channel="http",
                                    frame_index=count,
                                    source_time_s=source_time_s,
                                    gps_snapshot=frame_gps_snapshot,
                                    diseases=diseases_for_log,
                                )
                    except Exception as e:
                        print(f"❌ HTTP 发送失败 ({e.__class__.__name__}): {str(e)}")

                # UDP 发送数据，用于甲方B平台
                if self.cfg.get("ENABLE_UDP") and self.udp_sender:
                    if count == 1:
                        print("🔍 UDP 发送准备:")
                        print(f"   udp_sender 对象: {self.udp_sender}")
                        print(f"   发送间隔: {self.udp_send_interval}秒")
                        print("   完整字段: 机器人状态/帧号/左右果树编号/时间/GPS/方位角/速度/相机高度/电压/电量")
                    try:
                        # 纯推流和固定果树事件不携带模型病害状态
                        udp_disease_detected = (
                            False
                            if raw_stream_only
                            or timeline_tree_event
                            or explicit_tree_indices is not None
                            else disease_detected
                        )
                        is_near_tree_event = tree_present
                        should_send_udp = (
                            bool(timeline_tree_event)
                            or tree_state_changed
                            or current_time - self.last_udp_send_time > self.udp_send_interval
                        )

                        if should_send_udp:
                            missing_fields = missing_udp_telemetry_fields(status_data, gps_dms)
                            if missing_fields:
                                self._log_missing_udp_telemetry(missing_fields, current_time)
                            else:
                                velocity_protocol = int(round(float(status_data['velocity']) * 10))
                                eyepoint_height_protocol = int(round(float(status_data['eyepoint_height']) * 100))
                                bat_voltage_protocol = int(round(float(status_data['bat_voltage']) * 10))
                                udp_status = map_common_status_to_udp(
                                    status_data["robot_status"],
                                    tree_present=is_near_tree_event,
                                )
                                success = self.udp_sender.send_robot_data(
                                    robot_status=udp_status,
                                    frame_index=count,
                                    lat_degree=lat_d, lat_minute=lat_m, lat_second=lat_s, lat_direction=lat_dir,
                                    lon_degree=lon_d, lon_minute=lon_m, lon_second=lon_s, lon_direction=lon_dir,
                                    azimuth=status_data['azimuth'],
                                    velocity=velocity_protocol,
                                    eyepoint_height=eyepoint_height_protocol,
                                    bat_voltage=bat_voltage_protocol,
                                    soc=status_data['soc'],
                                    disease_detected=udp_disease_detected,
                                    tree_event=timeline_tree_event,
                                    explicit_tree_indices=explicit_tree_indices,
                                )
                                if success:
                                    self.udp_send_count += 1
                                    if tree_present:
                                        self._log_gps_event(
                                            event_type="tree",
                                            channel="udp",
                                            frame_index=count,
                                            source_time_s=source_time_s,
                                            gps_snapshot=frame_gps_snapshot,
                                            tree_event=tree_event,
                                        )
                                    elif udp_disease_detected:
                                        self._log_gps_event(
                                            event_type="disease",
                                            channel="udp",
                                            frame_index=count,
                                            source_time_s=source_time_s,
                                            gps_snapshot=frame_gps_snapshot,
                                            diseases=diseases_for_log,
                                        )
                                self.last_udp_send_time = current_time
                                if tree_present:
                                    if (
                                        timeline_tree_event
                                        and self.cfg.get("UDP_TREE_EVENT_DEBUG", False)
                                    ):
                                        direction_text = "正放" if timeline_tree_event["direction"] > 0 else "倒放"
                                        print(
                                            f"📡 UDP 数据 | {timeline_tree_event['tree_code']} | "
                                            f"原视频 {timeline_tree_event['event_time']:.0f}s | {direction_text} | "
                                            f"{self.udp_sender.get_last_packet_summary()}"
                                        )
                                    else:
                                        print(f"📡 UDP 数据 | {self.udp_sender.get_last_packet_summary()}")
                                elif self.cfg.get("UDP_VERBOSE_LOG", False):
                                    log_interval = max(1, int(self.cfg.get("UDP_LOG_INTERVAL", 5)))
                                    if self.udp_send_count == 1 or self.udp_send_count % log_interval == 0:
                                        print(f"📡 UDP 数据 | {self.udp_sender.get_last_packet_summary()}")
                                if udp_disease_detected:
                                    print(f"📡 UDP 上报 | 帧:{count} | 病害检测")
                    except Exception as e:
                        print(f"❌ UDP 发送失败 ({e.__class__.__name__}): {str(e)}")

                # RTMP推流
                if self.cfg["ENABLE_RTMP"] and self.rtmp_sender and rtmp_initialized:
                    frame_to_push = resize_frame_for_stream(im0s, push_w, push_h)
                    self.rtmp_sender.send_frame(frame_to_push)

                if self.rate_check:
                    time.sleep(1.0 / self.rate)

                if not self.cfg.get("HEADLESS", False):
                    self.send_img.emit(im0)
                    self.send_raw.emit(im0s)
                self.send_statistic.emit(statistic_dic)

        except Exception as e:
            error_msg = f'{e.__class__.__name__}: {str(e)}'
            self.send_msg.emit(f'错误：{error_msg}')
            import traceback
            traceback.print_exc()
            print(f"\n❌ 检测线程异常: {error_msg}")
        finally:
            self.cleanup_resources(stop_gps=False)

class MainWindow(QMainWindow, Ui_mainWindow):
    def __init__(self, config=None, parent=None):
        super(MainWindow, self).__init__(parent)
        self.setupUi(self)
        self.showMaximized()# 启动时默认最大化窗口（全屏效果） 
        self.cfg = config if config else CONFIG
        self.m_flag = False
        self._closing = False
        self.realtime_value_labels = {}
        self.realtime_name_labels = {}
        self.latest_raw_frame = None
        self.recording_mode = None
        self.video_recorder = VideoRecorder()
        self.record_timer = QTimer(self)
        self.record_timer.timeout.connect(self.record_next_frame)
        self.setWindowFlags(Qt.CustomizeWindowHint | Qt.WindowStaysOnTopHint)
        self.setup_compact_left_panel()
        self.setup_recording_controls()

        self.minButton.clicked.connect(self.showMinimized)
        self.maxButton.clicked.connect(self.max_or_restore)
        self.closeButton.clicked.connect(self.close)

        self.qtimer = QTimer(self)
        self.qtimer.setSingleShot(True)
        self.qtimer.timeout.connect(lambda: self.statistic_label.clear())

        self.comboBox.clear()
        self.pt_list = [f for f in os.listdir('./pt') if f.endswith('.pt')] if os.path.exists('./pt') else []
        self.pt_list.sort(key=lambda x: os.path.getsize('./pt/' + x) if os.path.exists('./pt/' + x) else 0)
        self.comboBox.addItems(self.pt_list)

        self.det_thread = DetThread(config=self.cfg)

        self.model_type = self.comboBox.currentText() if self.pt_list else self.cfg["WEIGHTS"]
        if not self.cfg.get("RAW_STREAM_ONLY", False):
            self.det_thread.weights = f"./pt/{self.model_type}" if self.pt_list else self.cfg["WEIGHTS"]
        self.det_thread.source = self.cfg["SOURCE"]
        self.det_thread.percent_length = self.progressBar.maximum()

        self.det_thread.send_raw.connect(self.handle_raw_frame)
        self.det_thread.send_img.connect(lambda x: self.show_image(x, self.out_video))
        self.det_thread.send_statistic.connect(self.show_statistic)
        self.det_thread.send_data.connect(self.show_realtime_data)
        self.det_thread.send_msg.connect(self.show_msg)
        self.det_thread.send_percent.connect(lambda x: self.progressBar.setValue(x))
        self.det_thread.send_fps.connect(lambda x: self.fps_label.setText(x))
        self.det_thread.finished.connect(self.handle_detection_finished)

        self.bind_signals()
        self.load_setting()
        self.start_background_data_receivers()

    def start_background_data_receivers(self):
        """窗口启动后立即接收真实数据，不要求先启动检测。"""
        self.det_thread._start_data_receivers()
        messages = []
        if self.det_thread.telemetry_receiver:
            messages.append(
                f"遥测 {self.cfg.get('TELEMETRY_SERIAL_PORT') or 'AUTO'} @ "
                f"{self.cfg.get('TELEMETRY_SERIAL_BAUDRATE', 9600)}"
            )
        if self.det_thread.gps_receiver:
            messages.append(
                f"旧GPS {self.cfg.get('GPS_SERIAL_PORT') or 'AUTO'} @ "
                f"{self.cfg.get('GPS_SERIAL_BAUDRATE', 9600)}"
            )
        if messages:
            self.statistic_msg("串口接收中: " + " | ".join(messages))

    def bind_signals(self):
        self.fileButton.clicked.connect(self.open_file)
        self.cameraButton.clicked.connect(self.chose_cam)
        self.rtspButton.clicked.connect(self.chose_rtsp)
        self.runButton.clicked.connect(self.run_or_continue)
        self.stopButton.clicked.connect(self.stop)
        self.comboBox.currentTextChanged.connect(self.change_model)
        self.horizontalModeButton.clicked.connect(lambda: self.set_detection_orientation(Qt.Horizontal))
        self.verticalModeButton.clicked.connect(lambda: self.set_detection_orientation(Qt.Vertical))
        self.recordButton.clicked.connect(self.toggle_recording)

    def load_setting(self):
        pass

    def setup_compact_left_panel(self):
        self.label_27.hide()
        self.label_28.hide()
        for widget in (self.label_8, self.checkBox, self.rateSpinBox, self.rateSlider, self.saveCheckBox):
            widget.hide()

        # 小屏设备使用滚动区域，避免左侧内容把主窗口最小高度撑出屏幕。
        self.horizontalLayout_7.removeWidget(self.groupBox_8)
        self.leftScrollArea = QScrollArea(self.groupBox_18)
        self.leftScrollArea.setObjectName("leftScrollArea")
        self.leftScrollArea.setWidgetResizable(True)
        self.leftScrollArea.setFrameShape(QFrame.NoFrame)
        self.leftScrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.leftScrollArea.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.leftScrollArea.setFixedWidth(334)
        self.leftScrollArea.setStyleSheet("""
QScrollArea#leftScrollArea {
    background: transparent;
    border: none;
}
QScrollArea#leftScrollArea > QWidget > QWidget {
    background: transparent;
}
""")
        self.leftScrollArea.verticalScrollBar().setStyleSheet("""
QScrollBar:vertical {
    background: rgba(255, 255, 255, 12);
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: rgba(225, 230, 226, 90);
    min-height: 36px;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    background: transparent;
    border: none;
    height: 0;
}
QScrollBar::up-arrow:vertical,
QScrollBar::down-arrow:vertical {
    background: transparent;
    width: 0;
    height: 0;
}
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
}
""")
        self.leftScrollArea.verticalScrollBar().setFixedWidth(8)
        self.leftScrollArea.setWidget(self.groupBox_8)
        self.horizontalLayout_7.insertWidget(0, self.leftScrollArea)

        self.groupBox_8.setMinimumWidth(300)
        self.groupBox_8.setMaximumWidth(16777215)
        self.groupBox_8.setStyleSheet("""
QGroupBox#groupBox_8 {
    background-color: rgba(52, 60, 57, 205);
    border: none;
    border-right: 1px solid rgba(255, 255, 255, 48);
    border-radius: 0;
}
""")
        self.verticalLayout_8.setSpacing(8)
        self.verticalLayout_8.setContentsMargins(12, 10, 12, 10)
        self.label_11.setText("巡检数据")
        self.label_11.setStyleSheet("""
QLabel {
    color: #f3f5f2;
    font: bold 18px "Microsoft YaHei";
    padding: 2px 0;
}
""")

        mode_layout = QHBoxLayout()
        mode_layout.setSpacing(8)
        self.horizontalModeButton = QPushButton("横向检测", self.groupBox_8)
        self.verticalModeButton = QPushButton("纵向检测", self.groupBox_8)
        self.horizontalModeButton.setToolTip("原始画面和检测画面左右排列")
        self.verticalModeButton.setToolTip("原始画面和检测画面上下排列")
        for button in (self.horizontalModeButton, self.verticalModeButton):
            button.setCheckable(True)
            button.setMinimumHeight(34)
            button.setCursor(Qt.PointingHandCursor)
        mode_layout.addWidget(self.horizontalModeButton)
        mode_layout.addWidget(self.verticalModeButton)
        self.verticalLayout_7.insertLayout(1, mode_layout)

        self.dataPanel = QFrame(self.groupBox_8)
        self.dataPanel.setObjectName("dataPanel")
        self.dataPanel.setStyleSheet("""
QFrame#dataPanel {
    background-color: rgba(27, 33, 31, 155);
    border: 1px solid rgba(255, 255, 255, 58);
    border-radius: 6px;
}
QLabel[role="panelTitle"] {
    color: #f4f6f3;
    font: bold 15px "Microsoft YaHei";
}
QLabel[role="modeBadge"] {
    background: transparent;
    border: none;
    color: #d9ded9;
    font-size: 17px;
}
QLabel[role="modeBadge"][source="real"] {
    color: #68c786;
}
QLabel[role="modeBadge"][source="virtual"] {
    color: #d1a34c;
}
QLabel[role="modeBadge"][source="mixed"] {
    color: #d1a34c;
}
QLabel[role="modeBadge"][source="waiting"] {
    color: #b5bdb7;
}
QLabel[role="modeBadge"][source="unknown"] {
    color: #9aa39d;
}
QLabel[role="sectionTitle"] {
    color: rgba(224, 230, 225, 145);
    font: bold 11px "Microsoft YaHei";
    padding-top: 5px;
}
QLabel[role="fieldName"] {
    font-family: "Microsoft YaHei";
    font-size: 13px;
    color: rgba(225, 230, 226, 158);
}
QLabel[role="fieldValue"] {
    font-family: "Microsoft YaHei";
    font-size: 13px;
    color: #f0f3ef;
}
QLabel[role="fieldValue"][available="false"] {
    color: rgba(225, 230, 226, 92);
}
QLabel[role="gpsValue"] {
    font-family: "DejaVu Sans Mono";
    font-size: 13px;
    color: #edf5ed;
    line-height: 1.3;
}
QLabel[role="gpsValue"][available="false"] {
    color: rgba(225, 230, 226, 92);
}
QFrame[role="divider"] {
    background-color: rgba(255, 255, 255, 28);
    border: none;
}
""")
        data_layout = QGridLayout(self.dataPanel)
        data_layout.setContentsMargins(12, 11, 12, 12)
        data_layout.setHorizontalSpacing(12)
        data_layout.setVerticalSpacing(6)
        data_layout.setColumnStretch(1, 1)

        panel_title = QLabel("实时遥测", self.dataPanel)
        panel_title.setProperty("role", "panelTitle")
        data_layout.addWidget(panel_title, 0, 0)
        self.data_source_badge = QLabel("●", self.dataPanel)
        self.data_source_badge.setProperty("role", "modeBadge")
        self.data_source_badge.setProperty("source", "waiting")
        self.data_source_badge.setToolTip("等待数据")
        self.data_source_badge.setFixedSize(20, 20)
        self.data_source_badge.setAlignment(Qt.AlignCenter)
        data_layout.addWidget(self.data_source_badge, 0, 1, Qt.AlignRight)

        gps_name = QLabel("GPS 坐标", self.dataPanel)
        gps_name.setProperty("role", "fieldName")
        gps_value = QLabel(EMPTY_VALUE, self.dataPanel)
        gps_value.setProperty("role", "gpsValue")
        gps_value.setProperty("available", False)
        gps_value.setWordWrap(True)
        gps_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        data_layout.addWidget(gps_name, 1, 0, Qt.AlignTop)
        data_layout.addWidget(gps_value, 1, 1)
        self.realtime_name_labels["gps"] = gps_name
        self.realtime_value_labels["gps"] = gps_value
        gps_name.setProperty("fieldTitle", "GPS 坐标")
        gps_name.setProperty(
            "fieldDescription",
            "电控统一遥测或旧 OPGPS 串口提供的实时位置",
        )
        gps_name.setToolTip(gps_name.property("fieldDescription"))
        gps_value.setToolTip(gps_name.toolTip())

        row = 2
        field_descriptions = {
            "robot_status": "电控上报的机器人通用运行状态",
            "velocity": "电控速度优先；缺失时才根据连续 GPS 坐标估算",
            "azimuth": "电控上报的机器人行进方位角",
            "camera_height": "相机视点相对地面的实时高度",
            "battery": "电控上报的剩余电量和电池电压",
            "fault": "电控故障码，0 表示无故障",
            "tree": "当前树及左右果树编号，编号 0 表示当前无树",
            "route": "当前巡检路线和路径点编号",
            "work_mode": "检测方式和真实/调试/仿真数据模式",
            "frame_index": "视觉主机当前处理的视频帧序号",
            "disease_count": "当前帧识别到的病害目标总数",
            "channels": "本次运行已经启用的数据与平台通道",
        }
        for section_title, fields in (
            ("设备状态", (
                ("robot_status", "机器人状态"),
                ("velocity", "速度"),
                ("azimuth", "方位"),
                ("camera_height", "相机高度"),
                ("battery", "电池"),
                ("fault", "故障码"),
            )),
            ("巡检任务", (
                ("tree", "果树"),
                ("route", "路线位置"),
                ("work_mode", "任务模式"),
                ("frame_index", "当前帧"),
                ("disease_count", "识别目标"),
                ("channels", "数据链路"),
            )),
        ):
            divider = QFrame(self.dataPanel)
            divider.setProperty("role", "divider")
            divider.setFixedHeight(1)
            data_layout.addWidget(divider, row, 0, 1, 2)
            row += 1
            section_label = QLabel(section_title, self.dataPanel)
            section_label.setProperty("role", "sectionTitle")
            data_layout.addWidget(section_label, row, 0, 1, 2)
            row += 1
            for key, title in fields:
                name_label = QLabel(title, self.dataPanel)
                name_label.setProperty("role", "fieldName")
                value_label = QLabel(EMPTY_VALUE, self.dataPanel)
                value_label.setProperty("role", "fieldValue")
                value_label.setProperty("available", False)
                value_label.setWordWrap(True)
                value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
                data_layout.addWidget(name_label, row, 0, Qt.AlignTop)
                data_layout.addWidget(value_label, row, 1)
                self.realtime_name_labels[key] = name_label
                self.realtime_value_labels[key] = value_label
                name_label.setProperty("fieldTitle", title)
                description = field_descriptions.get(key, title)
                name_label.setProperty("fieldDescription", description)
                name_label.setToolTip(description)
                value_label.setToolTip(description)
                row += 1

        for key in self.realtime_name_labels:
            self.set_realtime_source(key, "unavailable")

        self.verticalLayout_7.insertWidget(2, self.dataPanel)
        self.setup_stream_resolution_control()
        # 实时遥测优先显示，阈值等低频设置放在其后，需要时可向下滚动。
        self.verticalLayout_8.removeItem(self.verticalLayout_7)
        self.verticalLayout_8.insertLayout(3, self.verticalLayout_7)
        self.resultWidget.setMinimumHeight(84)
        self.resultWidget.setMaximumHeight(120)
        self.resultWidget.setStyleSheet("""
QListWidget{
    background-color: rgba(12, 28, 77, 0);
    border: 1px solid rgba(200, 200, 200, 90);
    border-radius: 4px;
    font-family: "Microsoft YaHei";
    font-size: 14px;
    color: rgb(218, 218, 218);
}
""")
        self.set_detection_orientation(Qt.Horizontal)

    def setup_stream_resolution_control(self):
        resolution_layout = QHBoxLayout()
        resolution_layout.setSpacing(8)
        resolution_layout.setContentsMargins(0, 0, 7, 0)

        resolution_label_widget = QLabel("推流分辨率", self.groupBox_8)
        resolution_label_widget.setMinimumWidth(92)
        resolution_label_widget.setMaximumWidth(92)
        resolution_label_widget.setStyleSheet("""
QLabel {
    color: rgb(218, 218, 218);
    font: bold 16px "Microsoft YaHei";
}
""")
        resolution_layout.addWidget(resolution_label_widget)

        self.streamResolutionCombo = QComboBox(self.groupBox_8)
        self.streamResolutionCombo.setObjectName("streamResolutionCombo")
        self.streamResolutionCombo.setMinimumHeight(35)
        self.streamResolutionCombo.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed,
        )
        self.streamResolutionCombo.setStyleSheet(self.comboBox.styleSheet())
        self.streamResolutionCombo.setToolTip("RTMP 输出尺寸；画面保持原比例")
        for key, label, _width, _height in COMMON_STREAM_RESOLUTIONS:
            self.streamResolutionCombo.addItem(label, key)

        configured_resolution = self.cfg.get("RTMP_RESOLUTION", "source")
        try:
            configured_resolution = normalize_resolution_key(configured_resolution)
        except ValueError:
            configured_resolution = "source"
            self.cfg["RTMP_RESOLUTION"] = configured_resolution
        selected_index = self.streamResolutionCombo.findData(configured_resolution)
        self.streamResolutionCombo.setCurrentIndex(max(0, selected_index))
        self.streamResolutionCombo.currentIndexChanged.connect(
            self.change_stream_resolution
        )
        resolution_layout.addWidget(self.streamResolutionCombo, 1)

        # 放在模型选择之后；遥测面板随后会被提升到它的下方。
        self.verticalLayout_8.insertLayout(2, resolution_layout)

    def change_stream_resolution(self, _index):
        resolution = self.streamResolutionCombo.currentData()
        if not resolution:
            return
        resolution = normalize_resolution_key(resolution)
        self.cfg["RTMP_RESOLUTION"] = resolution
        self.statistic_msg(f"推流分辨率：{resolution_label(resolution)}")

    def setup_recording_controls(self):
        self.recordButton = QPushButton("●", self.groupBox_5)
        self.recordButton.setObjectName("recordButton")
        self.recordButton.setFixedSize(55, 28)
        self.recordButton.setCursor(Qt.PointingHandCursor)
        self.recordButton.setToolTip("录制")
        self.recordButton.setProperty("recording", False)
        self.recordButton.setStyleSheet("""
QPushButton#recordButton {
    color: #ef625b;
    background-color: rgba(48, 148, 243, 0);
    border: none;
    border-radius: 3px;
    font-size: 19px;
    padding-bottom: 2px;
}
QPushButton#recordButton:hover {
    background-color: rgba(48, 148, 243, 80);
}
QPushButton#recordButton[recording="true"] {
    color: white;
    background-color: rgba(195, 55, 50, 210);
}
""")
        self.horizontalLayout_8.addWidget(self.recordButton)

        self.record_menu = QMenu(self)
        camera_action = QAction(QIcon("./icon/摄像头开.png"), "摄像头画面", self)
        window_action = QAction(QIcon("./icon/图片1.png"), "当前界面", self)
        camera_action.triggered.connect(
            lambda checked=False: self.start_recording("camera")
        )
        window_action.triggered.connect(
            lambda checked=False: self.start_recording("window")
        )
        self.record_menu.addAction(camera_action)
        self.record_menu.addAction(window_action)

    def toggle_recording(self):
        if self.video_recorder.active:
            self.stop_recording()
            return
        menu_position = self.recordButton.mapToGlobal(
            QPoint(0, self.recordButton.height())
        )
        self.record_menu.exec_(menu_position)

    def start_recording(self, mode):
        if mode == "camera":
            if self.latest_raw_frame is None or not self.det_thread.isRunning():
                self.statistic_msg("请先运行摄像头画面，再开始录像")
                return
            frame = self.latest_raw_frame.copy()
            fps = self.current_source_fps()
            prefix = "camera"
            mode_name = "摄像头画面"
        elif mode == "window":
            frame = self.capture_window_frame()
            if frame is None:
                self.statistic_msg("当前界面抓取失败，无法开始录像")
                return
            fps = 15.0
            prefix = "ui"
            mode_name = "当前界面"
        else:
            raise ValueError(f"未知录像模式: {mode}")

        milliseconds = int(time.time() * 1000) % 1000
        timestamp = f'{time.strftime("%Y%m%d_%H%M%S")}_{milliseconds:03d}'
        output_path = Path("result") / "recordings" / f"{prefix}_{timestamp}.mp4"
        try:
            self.video_recorder.start(
                output_path,
                (frame.shape[1], frame.shape[0]),
                fps,
            )
            self.video_recorder.write(frame)
        except (OSError, RuntimeError, ValueError) as exc:
            self.video_recorder.stop()
            self.statistic_msg(f"录像启动失败：{exc}")
            return

        self.recording_mode = mode
        self.record_timer.start(max(1, round(1000 / fps)))
        self.recordButton.setProperty("recording", True)
        self.recordButton.setToolTip("停止录制")
        self.recordButton.style().unpolish(self.recordButton)
        self.recordButton.style().polish(self.recordButton)
        self.statistic_msg(f"正在录制{mode_name}")

    def stop_recording(self, show_message=True):
        self.record_timer.stop()
        output_path = self.video_recorder.stop()
        self.recording_mode = None
        self.recordButton.setProperty("recording", False)
        self.recordButton.setToolTip("录制")
        self.recordButton.style().unpolish(self.recordButton)
        self.recordButton.style().polish(self.recordButton)
        if show_message and output_path is not None:
            self.statistic_msg(f"录像已保存：{output_path}")
        return output_path

    def record_next_frame(self):
        if not self.video_recorder.active:
            return
        if self.recording_mode == "camera":
            frame = None if self.latest_raw_frame is None else self.latest_raw_frame.copy()
        else:
            frame = self.capture_window_frame()
        if frame is None:
            self.stop_recording(show_message=False)
            self.statistic_msg("录像已停止：无法获取画面")
            return
        try:
            self.video_recorder.write(frame)
        except (OSError, RuntimeError, ValueError) as exc:
            self.stop_recording(show_message=False)
            self.statistic_msg(f"录像写入失败：{exc}")

    def current_source_fps(self):
        fps = 0.0
        if self.det_thread.vid_cap is not None:
            fps = float(self.det_thread.vid_cap.get(cv2.CAP_PROP_FPS) or 0)
        if not np.isfinite(fps) or fps <= 0:
            fps = 25.0
        return min(fps, 60.0)

    def capture_window_frame(self):
        pixmap = self.grab()
        if pixmap.isNull():
            return None
        image = pixmap.toImage().convertToFormat(QImage.Format_RGBA8888)
        width, height = image.width(), image.height()
        pointer = image.bits()
        pointer.setsize(image.byteCount())
        rgba = np.frombuffer(pointer, dtype=np.uint8).reshape(
            height, image.bytesPerLine() // 4, 4
        )[:, :width]
        return cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)

    def handle_raw_frame(self, frame):
        self.latest_raw_frame = frame.copy()
        self.show_image(frame, self.raw_video)

    def handle_detection_finished(self):
        self.streamResolutionCombo.setEnabled(True)
        if self.recording_mode != "camera":
            return
        output_path = self.stop_recording(show_message=False)
        if output_path is not None:
            self.statistic_msg(f"视频源已结束，录像已保存：{output_path}")

    def set_detection_orientation(self, orientation):
        self.splitter.setOrientation(orientation)
        if orientation == Qt.Horizontal:
            self.label_6.setText("横向检测")
            self.raw_video.setToolTip("原始画面")
            self.out_video.setToolTip("检测结果")
            self.splitter.setSizes([1, 1])
        else:
            self.label_6.setText("纵向检测")
            self.raw_video.setToolTip("上方：原始画面")
            self.out_video.setToolTip("下方：检测结果")
            self.splitter.setSizes([1, 1])
        self.horizontalModeButton.setChecked(orientation == Qt.Horizontal)
        self.verticalModeButton.setChecked(orientation == Qt.Vertical)
        self.refresh_detection_mode_style()

    def refresh_detection_mode_style(self):
        active_style = """
QPushButton {
    background-color: rgba(68, 126, 85, 185);
    border: 1px solid rgba(157, 195, 165, 150);
    border-radius: 4px;
    color: #edf5ee;
    font: bold 14px "Microsoft YaHei";
}
QPushButton:hover {
    background-color: rgba(78, 143, 96, 205);
}
QPushButton:pressed {
    background-color: rgba(56, 109, 72, 215);
}
"""
        inactive_style = """
QPushButton {
    background-color: rgba(202, 215, 205, 28);
    border: 1px solid rgba(171, 194, 177, 82);
    border-radius: 4px;
    color: #d6ded8;
    font: bold 14px "Microsoft YaHei";
}
QPushButton:hover {
    background-color: rgba(75, 133, 89, 92);
    border-color: rgba(157, 195, 165, 125);
}
QPushButton:pressed {
    background-color: rgba(61, 115, 75, 130);
}
"""
        self.horizontalModeButton.setStyleSheet(active_style if self.horizontalModeButton.isChecked() else inactive_style)
        self.verticalModeButton.setStyleSheet(active_style if self.verticalModeButton.isChecked() else inactive_style)

    def statistic_msg(self, msg):
        self.statistic_label.setText(msg)

    def show_msg(self, msg):
        self.runButton.setChecked(Qt.Unchecked)
        self.statistic_msg(msg)

    def change_model(self, x):
        self.det_thread.weights = f"./pt/{x}"
        self.statistic_msg(f'模型：{x}')

    def open_file(self):
        name, _ = QFileDialog.getOpenFileName(self, '选择文件', os.getcwd(), 'Video/Image(*.mp4 *.avi *.jpg *.png)')
        if name:
            self.det_thread.source = name
            self.statistic_msg(f'加载：{os.path.basename(name)}')
            self.stop()

    def chose_cam(self):
        self.stop()
        self.det_thread.source = '0'
        self.statistic_msg('摄像头模式')

    def chose_rtsp(self):
        self.rtsp_win = Window()
        self.rtsp_win.show()
        self.rtsp_win.rtspButton.clicked.connect(lambda: self.load_rtsp(self.rtsp_win.rtspEdit.text()))

    def load_rtsp(self, ip):
        self.det_thread.source = ip
        self.statistic_msg(f'RTSP：{ip}')
        self.rtsp_win.close()

    def run_or_continue(self):
        if self._is_unavailable_camera_source(self.det_thread.source):
            self.runButton.setChecked(Qt.Unchecked)
            self.statistic_msg(f'摄像头 {self.det_thread.source} 打开失败，请选择本地图片/视频或更换摄像头编号')
            return
        self.det_thread.jump_out = False
        self.det_thread.is_continue = True
        if not self.det_thread.isRunning():
            self.streamResolutionCombo.setEnabled(False)
            self.det_thread.start()
        self.statistic_msg('运行中')

    @staticmethod
    def _is_unavailable_camera_source(source):
        if not str(source).isnumeric():
            return False
        camera_id = int(source)
        # Windows 优先使用 DirectShow，其他系统交给 OpenCV 自动选择
        backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else 0
        cap = cv2.VideoCapture(camera_id, backend) if backend else cv2.VideoCapture(camera_id)
        ok = cap.isOpened()
        if ok:
            ok, frame = cap.read()
            ok = ok and frame is not None
        cap.release()
        return not ok

    def stop(self):
        recording_path = None
        if self.recording_mode == "camera":
            recording_path = self.stop_recording(show_message=False)
        self.det_thread.jump_out = True
        self.det_thread.is_continue = False
        if recording_path is None:
            self.statistic_msg('已停止')
        else:
            self.statistic_msg(f'已停止，录像已保存：{recording_path}')

    def shutdown(self):
        if self._closing:
            return
        self._closing = True
        print("ℹ️ 正在关闭界面并释放巡检资源")

        self.qtimer.stop()
        self.stop_recording(show_message=False)
        if hasattr(self, "rtsp_win") and self.rtsp_win is not None:
            try: self.rtsp_win.close()
            except: pass

        self.det_thread.jump_out = True
        self.det_thread.is_continue = True

        # 串口接收线程可能早于检测启动，先停止它们再等待检测线程退出。
        for name, receiver in (
            ("遥测", self.det_thread.telemetry_receiver),
            ("GPS", self.det_thread.gps_receiver),
        ):
            if receiver:
                try:
                    receiver.stop()
                except Exception as exc:
                    print(f"⚠️ {name} 接收线程关闭失败: {exc}")

        if self.det_thread.isRunning():
            if not self.det_thread.wait(5000):
                print("⚠️ 检测线程关闭超时，强制终止")
                self.det_thread.terminate()
                if not self.det_thread.wait(2000):
                    print("⚠️ 检测线程仍未退出，直接结束进程")
                    os._exit(0)

        self.det_thread.cleanup_resources(stop_gps=True)
        print("✅ 巡检资源已释放，程序退出")

    def max_or_restore(self):
        self.showMaximized() if self.maxButton.isChecked() else self.showNormal()

    @staticmethod
    def show_image(img_src, label):
        ih, iw, _ = img_src.shape
        w, h = label.width(), label.height()
        scale = min(w / iw, h / ih)
        nw, nh = int(iw * scale), int(ih * scale)
        resized = cv2.resize(img_src, (nw, nh))
        resized = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        qimg = QImage(resized.data, nw, nh, nw * 3, QImage.Format_RGB888)
        label.setPixmap(QPixmap.fromImage(qimg))
        label.setAlignment(Qt.AlignCenter)

    @staticmethod
    def format_gps_dms(gps_dms):
        return build_realtime_view({"gps_dms": gps_dms})["values"]["gps"]

    def set_realtime_value(self, key, value):
        label = self.realtime_value_labels.get(key)
        if label is not None:
            display_value = EMPTY_VALUE if value is None or value == "" else str(value)
            available = display_value != EMPTY_VALUE
            label.setText(display_value)
            label.setProperty("available", available)
            label.style().unpolish(label)
            label.style().polish(label)

    def set_realtime_source(self, key, source):
        label = self.realtime_name_labels.get(key)
        if label is None:
            return
        source_visuals = {
            "real": ("#68c786", "真实数据"),
            "virtual": ("#d1a34c", "虚拟数据"),
            "estimated": ("#d1a34c", "GPS 坐标估算"),
            "mixed": ("#d1a34c", "真实与虚拟数据混合"),
            "unavailable": ("#737d76", "暂无数据"),
            "unknown": ("#9aa39d", "数据来源未知"),
        }
        color, source_status = source_visuals.get(source, source_visuals["unknown"])
        title = str(label.property("fieldTitle") or key)
        description = str(label.property("fieldDescription") or title)
        label.setText(
            f'<span style="color:{color}; font-size:10px;">●</span>&nbsp;{title}'
        )
        tooltip = f"{description}\n当前来源：{source_status}"
        label.setToolTip(tooltip)
        value_label = self.realtime_value_labels.get(key)
        if value_label is not None:
            value_label.setToolTip(tooltip)

    def show_realtime_data(self, data):
        view = build_realtime_view(data)
        for key, value in view["values"].items():
            self.set_realtime_value(key, value)
            self.set_realtime_source(
                key, view["field_sources"].get(key, "unknown")
            )

        self.data_source_badge.setText("●")
        source_tooltips = {
            "real": "真实遥测正常",
            "virtual": "当前使用虚拟数据",
            "mixed": "真实数据优先，部分字段由虚拟数据补齐",
            "waiting": "等待数据",
            "unknown": "状态未知",
        }
        self.data_source_badge.setToolTip(
            source_tooltips.get(view["data_source"], "数据状态正常")
        )
        self.data_source_badge.setProperty("source", view["data_source"])
        self.data_source_badge.style().unpolish(self.data_source_badge)
        self.data_source_badge.style().polish(self.data_source_badge)

    def show_statistic(self, statistic_dic):
        self.resultWidget.clear()
        has_result = False
        for k, v in statistic_dic.items():
            if v > 0:
                self.resultWidget.addItem(f'{k}：{v} 个')
                has_result = True
        if not has_result:
            self.resultWidget.addItem('暂无病害目标')

    def closeEvent(self, event):
        self.shutdown()
        event.accept()
        app = QApplication.instance()
        if app is not None:
            QTimer.singleShot(0, app.quit)


def should_run_headless(args):
    if args.headless:
        return True
    if sys.platform.startswith("linux"):
        return not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return False


def run_headless(config):
    config["HEADLESS"] = True
    app = QCoreApplication.instance() or QCoreApplication(sys.argv[:1])
    worker = DetThread(config=config)
    last_log = {"time": 0.0}

    def log_fps(msg):
        print(f"[headless] {msg}")

    def log_message(msg):
        print(f"[headless] {msg}")

    def log_data(data):
        now = time.time()
        if now - last_log["time"] < 5:
            return
        last_log["time"] = now
        status = data.get("status") or {}
        velocity = status.get("velocity")
        soc = status.get("soc")
        velocity_text = "--" if velocity is None else f"{float(velocity):.2f}m/s"
        soc_text = "--" if soc is None else f"{soc}%"
        print(
            "[headless] "
            f"帧:{data.get('frame_index', '--')} | "
            f"目标:{data.get('disease_count', 0)} | "
            f"速度:{velocity_text} | "
            f"电量:{soc_text}"
        )

    worker.send_fps.connect(log_fps)
    worker.send_msg.connect(log_message)
    worker.send_data.connect(log_data)
    print("[headless] 无界面模式启动：跳过窗口和视频渲染，仅执行检测/推流/上报")
    try:
        worker.run()
    except KeyboardInterrupt:
        print("[headless] 收到停止信号，正在清理资源")
        worker.jump_out = True
    finally:
        worker.cleanup_resources(stop_gps=True)
        app.quit()
    return 0


if __name__ == "__main__":
    # 如果需要命令行覆盖配置，可以在这里解析 args 并更新 CONFIG 字典
    # 例如: python main.py --http-url "http://new-server.com"
    parser = argparse.ArgumentParser()
    parser.add_argument('--preset', type=str, default=None, choices=PRESET_NAMES,
                        help='配置方案：client_a(甲方A) | client_b(甲方B) | both(同时对接)')
    parser.add_argument('--data-mode', type=str, default=None, choices=DATA_MODES,
                        help='数据来源：real(全真实) | debug(真实优先/缺失虚拟) | simulation(全虚拟)')
    parser.add_argument('--http-url', type=str, default=None, help='覆盖 HTTP URL')
    parser.add_argument('--rtmp-url', type=str, default=None, help='覆盖 RTMP URL')
    parser.add_argument('--source', type=str, default=None, help='覆盖输入源，例如 0、视频路径、图片路径或 RTSP 地址')
    parser.add_argument('--raw-stream-only', action='store_true', help='只推送原始视频，跳过YOLO识别')
    parser.add_argument('--detect-stream', action='store_true', help='强制启用YOLO识别，覆盖预设中的纯推流模式')
    parser.add_argument('--auto-start', action='store_true', help='启动窗口后自动开始检测')
    parser.add_argument('--headless', action='store_true', help='无图形界面运行，适合未接显示器的部署环境')
    parser.add_argument('--enable-telemetry-serial', action='store_true', help='启用 58 字节电控统一遥测串口')
    parser.add_argument('--telemetry-port', type=str, default=None, help='覆盖电控遥测串口，例如 /dev/ttyTELEMETRY_IN 或 COM3')
    parser.add_argument('--telemetry-baudrate', type=int, default=None, help='覆盖电控遥测串口波特率')
    parser.add_argument('--telemetry-stale-timeout', type=float, default=None, help='覆盖电控遥测失效时间，单位秒')
    parser.add_argument('--no-telemetry-auto-detect', action='store_true', help='关闭电控遥测串口自动查找，仅使用指定端口')
    parser.add_argument('--enable-gps-serial', action='store_true', help='启用 GPS 串口接收')
    parser.add_argument('--gps-port', type=str, default=None, help='覆盖 GPS 串口，例如 /dev/ttyUSB0 或 COM3')
    parser.add_argument('--gps-baudrate', type=int, default=None, help='覆盖 GPS 串口波特率')
    parser.add_argument('--gps-stale-timeout', type=float, default=None, help='覆盖 GPS 数据失效时间，单位秒')
    parser.add_argument('--no-gps-auto-detect', action='store_true', help='关闭 GPS 串口自动查找，仅使用指定端口')
    args = parser.parse_args()

    # 如果命令行指定了配置方案，则覆盖默认值
    if args.preset:
        CONFIG.clear()
        CONFIG.update(build_config(args.preset))
        print(f"✅ 使用配置方案: {args.preset}")

    # 如果命令行提供了其他参数，则更新 CONFIG
    if args.http_url:
        CONFIG["HTTP_URL"] = args.http_url
        CONFIG["ENABLE_HTTP"] = True # 自动开启 HTTP
    if args.rtmp_url:
        CONFIG["RTMP_URL"] = args.rtmp_url
        CONFIG["ENABLE_RTMP"] = True # 自动开启 RTMP
    if args.data_mode:
        CONFIG["DATA_MODE"] = args.data_mode
    if args.source:
        CONFIG["SOURCE"] = args.source
    if args.raw_stream_only:
        CONFIG["RAW_STREAM_ONLY"] = True
    if args.detect_stream:
        CONFIG["RAW_STREAM_ONLY"] = False
    if args.enable_telemetry_serial:
        CONFIG["ENABLE_TELEMETRY_SERIAL"] = True
    if args.telemetry_port:
        CONFIG["TELEMETRY_SERIAL_PORT"] = args.telemetry_port
    if args.telemetry_baudrate is not None:
        CONFIG["TELEMETRY_SERIAL_BAUDRATE"] = args.telemetry_baudrate
    if args.telemetry_stale_timeout is not None:
        CONFIG["TELEMETRY_STALE_TIMEOUT"] = args.telemetry_stale_timeout
    if args.no_telemetry_auto_detect:
        CONFIG["TELEMETRY_SERIAL_AUTO_DETECT"] = False
    if args.enable_gps_serial:
        CONFIG["ENABLE_GPS_SERIAL"] = True
    if args.gps_port:
        CONFIG["GPS_SERIAL_PORT"] = args.gps_port
    if args.gps_baudrate is not None:
        CONFIG["GPS_SERIAL_BAUDRATE"] = args.gps_baudrate
    if args.gps_stale_timeout is not None:
        CONFIG["GPS_STALE_TIMEOUT"] = args.gps_stale_timeout
    if args.no_gps_auto_detect:
        CONFIG["GPS_SERIAL_AUTO_DETECT"] = False

    if should_run_headless(args):
        sys.exit(run_headless(CONFIG))

    app = QApplication(sys.argv)
    # 将配置好的 CONFIG 字典传给主窗口
    win = MainWindow(config=CONFIG)
    app.aboutToQuit.connect(win.shutdown)
    win.show()

    # 默认不自动启动，避免 Windows 上没有摄像头时反复触发 Camera Error 0
    if args.auto_start:
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(1000, win.run_or_continue)

    sys.exit(app.exec_())
