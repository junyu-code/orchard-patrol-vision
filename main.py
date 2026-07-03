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

CONFIG = build_config()

from PyQt5.QtWidgets import QApplication, QMainWindow, QFileDialog, QMenu, QAction, QListWidgetItem, QLabel, QVBoxLayout, QWidget, QSizePolicy, QStyleFactory
from PyQt5.QtCore import Qt, QPoint, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap, QIcon, QFont

from main_win.win import Ui_mainWindow
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
    send_msg = pyqtSignal(str)
    send_percent = pyqtSignal(int)
    send_fps = pyqtSignal(str)

    def __init__(self, config=None):
        super(DetThread, self).__init__()
        
        # 使用传入的配置，如果没有则使用全局默认 CONFIG
        self.cfg = config if config else CONFIG
        
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
        if VirtualSensorSimulator:
            self.sensor_sim = VirtualSensorSimulator(
                lat_decimal=self.cfg.get("SIM_BASE_LAT"),
                lon_decimal=self.cfg.get("SIM_BASE_LON"),
                use_system_location=self.cfg.get("USE_SYSTEM_LOCATION", False),
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
        self.patrol_timeline = self._build_patrol_timeline()
        # -----------------------------

        # 1. 初始化串口
        if self.cfg["ENABLE_SERIAL"] and SerialSender is not None:
            try:
                self.serial_sender = SerialSender(port=self.cfg["SERIAL_PORT"], baudrate=self.cfg["BAUDRATE"])
                self.serial_sender.open_serial()
                print(f"✅ 串口已打开: {self.cfg['SERIAL_PORT']}")
            except Exception as e:
                print(f"❌ 串口打开失败: {e.__class__.__name__}: {e}")
                self.serial_sender = None

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
                        simulate_tree_events=self.cfg.get("SIMULATE_TREE_EVENTS", False),
                        tree_interval=self.cfg.get("TREE_INTERVAL", 8),
                        tree_jitter=self.cfg.get("TREE_JITTER", 2),
                        tree_hold_frames=self.cfg.get("TREE_HOLD_FRAMES", 5),
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

    def _should_pingpong_source(self):
        """仅对本地演示视频启用正放/倒放循环。"""
        if not self.cfg.get("PINGPONG_SOURCE", False):
            return False
        source = str(self.source)
        if source.isnumeric() or source.lower().startswith(('rtsp://', 'rtmp://', 'http://', 'https://')):
            return False
        expected_name = str(self.cfg.get("PATROL_SOURCE_NAME", "")).lower()
        return not expected_name or Path(source).name.lower() == expected_name

    def cleanup_resources(self):
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
        print(f"   工作模式: {'原始视频推流' if raw_stream_only else 'YOLO识别'}")
        if not raw_stream_only:
            print(f"   模型: {self.weights}")
        print(f"   源: {self.source}")
        print(f"   HTTP: {'✅' if self.http_sender else '❌'} | RTMP: {'✅' if self.rtmp_sender else '❌'} | UDP: {'✅' if self.udp_sender else '❌'}")
        print("="*50)
        
        try:
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
                    
                    max_push_width = int(self.cfg.get("RTMP_MAX_WIDTH", 1280))
                    if w > max_push_width:
                        ratio = max_push_width / w
                        push_w = max_push_width
                        push_h = int(h * ratio)
                        # 确保宽高是偶数（编码器要求）
                        push_w = push_w - (push_w % 2)
                        push_h = push_h - (push_h % 2)
                    else:
                        push_w, push_h = w, h
                    
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
                                im0 = plot_one_box_chinese(xyxy, im0, label=label, color=colors(c, True), line_thickness=line_thickness)

                # HTTP 发送数据
                if self.cfg["ENABLE_HTTP"] and self.http_sender:
                    try:
                        count_canker = statistic_dic.get("溃疡病", 0)
                        count_huanglong = statistic_dic.get("黄龙病", 0)
                        count_anthrac = statistic_dic.get("炭疽病", 0)

                        conf_canker = max_conf_dic.get("溃疡病", 0.0)
                        conf_huanglong = max_conf_dic.get("黄龙病", 0.0)
                        conf_anthrac = max_conf_dic.get("炭疽病", 0.0)

                        is_detecting = (count_canker + count_huanglong + count_anthrac) > 0

                        if self.sensor_sim:
                            self.sensor_sim.update(count, is_near_tree=is_detecting)
                            lat_d, lat_m, lat_s, lat_dir, lon_d, lon_m, lon_s, lon_dir = self.sensor_sim.get_gps_dms()
                            status_data = self.sensor_sim.get_status_data()
                        else:
                            lat_d, lat_m, lat_s, lat_dir = 39, 54, 20, "N"
                            lon_d, lon_m, lon_s, lon_dir = 116, 23, 29, "E"
                            status_data = {"velocity":0, "azimuth":0, "bat_voltage":24, "soc":85, "route_index":1, "waypoint_index":0, "eyepoint_height":1.5}

                        current_time = time.time()

                        # 修改判断逻辑：
                        # 1. 必须检测到病害 (is_detecting)
                        # 2. 且距离上次发送超过指定间隔 (current_time - self.last_http_send_time > self.http_send_interval)
                        # 3. 定期心跳500帧（即使没病害）
                        should_send = (is_detecting or count % 500 == 0) and (current_time - self.last_http_send_time > self.http_send_interval)

                        if should_send:
                            frame_to_send = im0
                            # frame_to_send = im0 if send_image_flag else None

                            self.http_sender.send_robot_with_disease(
                                robot_id="ROBOT_001",
                                robot_status=1,
                                frame_index=count,
                                route_index=status_data['route_index'],
                                waypoint_index=status_data['waypoint_index'],
                                tree_index=0,
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
                                image_frame=frame_to_send
                            )

                            # 更新上次发送时间
                            self.last_http_send_time = current_time
                            print(f"📤 HTTP 上报 | 帧:{count} | 病害:{count_canker+count_huanglong+count_anthrac}")
                        else:
                            # 可选：打印跳过日志，调试用，正式运行可注释掉
                            # if is_detecting:
                            #     print(f"⏭️ HTTP 跳过 (频率限制) | 帧:{count}")
                            pass
                    except Exception as e:
                        print(f"❌ HTTP 发送失败 ({e.__class__.__name__}): {str(e)}")

                # UDP 发送数据 (新增 - 用于甲方B)
                if self.cfg.get("ENABLE_UDP") and self.udp_sender:
                    if count == 1:  # 第一帧时打印调试信息
                        print(f"🔍 UDP 发送准备:")
                        print(f"   udp_sender 对象: {self.udp_sender}")
                        print(f"   发送间隔: {self.udp_send_interval}秒")
                        print(f"   完整字段: 机器人状态/帧号/左右果树编号/时间/GPS/方位角/速度/相机高度/电压/电量")
                    try:
                        count_canker = statistic_dic.get("溃疡病", 0)
                        count_huanglong = statistic_dic.get("黄龙病", 0)
                        count_anthrac = statistic_dic.get("炭疽病", 0)
                        # 纯推流模式没有识别结果，病害状态固定为 False，只保留UDP链路心跳。
                        is_detecting = False if raw_stream_only else (count_canker + count_huanglong + count_anthrac) > 0
                        tree_event = None
                        if self.patrol_timeline:
                            tree_event = self.patrol_timeline.consume_event(
                                playback_time=getattr(dataset, "current_source_time", None),
                                playback_direction=getattr(dataset, "playback_direction", 1),
                                traversal_index=getattr(dataset, "traversal_index", 0),
                            )
                            if tree_event:
                                is_detecting = False
                        is_near_tree_event = bool(tree_event)

                        # 获取传感器数据
                        if self.sensor_sim:
                            self.sensor_sim.update(count, is_near_tree=is_detecting or is_near_tree_event)
                            lat_d, lat_m, lat_s, lat_dir, lon_d, lon_m, lon_s, lon_dir = self.sensor_sim.get_gps_dms()
                            status_data = self.sensor_sim.get_status_data()
                        else:
                            lat_d, lat_m, lat_s, lat_dir = 39, 54, 20, "N"
                            lon_d, lon_m, lon_s, lon_dir = 116, 23, 29, "E"
                            status_data = {"velocity":0.0, "azimuth":0, "bat_voltage":24.0, "soc":85, "eyepoint_height":1.5}

                        current_time = time.time()
                        velocity_protocol = int(round(float(status_data['velocity']) * 10))
                        eyepoint_height_protocol = int(round(float(status_data['eyepoint_height']) * 100))
                        bat_voltage_protocol = int(round(float(status_data['bat_voltage']) * 10))

                        # UDP 发送策略：甲方B固定果树事件立即上报，其余时间每秒发送巡检心跳
                        should_send_udp = bool(tree_event) or (current_time - self.last_udp_send_time > self.udp_send_interval)

                        if should_send_udp:
                            success = self.udp_sender.send_robot_data(
                                robot_status=1 if is_near_tree_event else 0,
                                frame_index=count,
                                lat_degree=lat_d, lat_minute=lat_m, lat_second=lat_s, lat_direction=lat_dir,
                                lon_degree=lon_d, lon_minute=lon_m, lon_second=lon_s, lon_direction=lon_dir,
                                azimuth=status_data['azimuth'],
                                velocity=velocity_protocol,
                                eyepoint_height=eyepoint_height_protocol,
                                bat_voltage=bat_voltage_protocol,
                                soc=status_data['soc'],
                                disease_detected=is_detecting,
                                tree_event=tree_event
                            )
                            if success:
                                self.udp_send_count += 1
                            self.last_udp_send_time = current_time
                            if tree_event:
                                if self.cfg.get("UDP_TREE_EVENT_DEBUG", False):
                                    direction_text = "正放" if tree_event["direction"] > 0 else "倒放"
                                    print(
                                        f"📡 UDP 数据 | {tree_event['tree_code']} | "
                                        f"原视频 {tree_event['event_time']:.0f}s | {direction_text} | "
                                        f"{self.udp_sender.get_last_packet_summary()}"
                                    )
                                else:
                                    print(f"📡 UDP 数据 | {self.udp_sender.get_last_packet_summary()}")
                            elif self.cfg.get("UDP_VERBOSE_LOG", False):
                                log_interval = max(1, int(self.cfg.get("UDP_LOG_INTERVAL", 5)))
                                if self.udp_send_count == 1 or self.udp_send_count % log_interval == 0:
                                    print(f"📡 UDP 数据 | {self.udp_sender.get_last_packet_summary()}")
                            if is_detecting:
                                print(f"📡 UDP 上报 | 帧:{count} | 病害检测")
                    except Exception as e:
                        print(f"❌ UDP 发送失败 ({e.__class__.__name__}): {str(e)}")

                # RTMP推流
                if self.cfg["ENABLE_RTMP"] and self.rtmp_sender and rtmp_initialized:
                    # 如果推流分辨率与当前画面不一致，需要缩放
                    if im0s.shape[1] != push_w or im0s.shape[0] != push_h:
                        frame_to_push = cv2.resize(im0s, (push_w, push_h))
                    else:
                        frame_to_push = im0s
                    self.rtmp_sender.send_frame(frame_to_push)

                if self.rate_check:
                    time.sleep(1.0 / self.rate)

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
            self.cleanup_resources()

class MainWindow(QMainWindow, Ui_mainWindow):
    def __init__(self, config=None, parent=None):
        super(MainWindow, self).__init__(parent)
        self.setupUi(self)
        self.showMaximized()# 启动时默认最大化窗口（全屏效果） 
        self.cfg = config if config else CONFIG
        self.m_flag = False
        self.setWindowFlags(Qt.CustomizeWindowHint | Qt.WindowStaysOnTopHint)

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

        self.det_thread.send_raw.connect(lambda x: self.show_image(x, self.raw_video))
        self.det_thread.send_img.connect(lambda x: self.show_image(x, self.out_video))
        self.det_thread.send_statistic.connect(self.show_statistic)
        self.det_thread.send_msg.connect(self.show_msg)
        self.det_thread.send_percent.connect(lambda x: self.progressBar.setValue(x))
        self.det_thread.send_fps.connect(lambda x: self.fps_label.setText(x))

        self.bind_signals()
        self.load_setting()

    def bind_signals(self):
        self.fileButton.clicked.connect(self.open_file)
        self.cameraButton.clicked.connect(self.chose_cam)
        self.rtspButton.clicked.connect(self.chose_rtsp)
        self.runButton.clicked.connect(self.run_or_continue)
        self.stopButton.clicked.connect(self.stop)
        self.comboBox.currentTextChanged.connect(self.change_model)

    def load_setting(self):
        pass

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
        self.det_thread.jump_out = True
        self.det_thread.is_continue = False
        self.statistic_msg('已停止')

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

    def show_statistic(self, statistic_dic):
        self.resultWidget.clear()
        for k, v in statistic_dic.items():
            if v > 0:
                self.resultWidget.addItem(f'{k}：{v} 个')

    def closeEvent(self, event):
        self.det_thread.jump_out = True
        self.det_thread.wait()
        event.accept()
        sys.exit(0)

if __name__ == "__main__":
    # 如果需要命令行覆盖配置，可以在这里解析 args 并更新 CONFIG 字典
    # 例如: python main.py --http-url "http://new-server.com"
    parser = argparse.ArgumentParser()
    parser.add_argument('--preset', type=str, default=None, choices=PRESET_NAMES,
                        help='配置方案：client_a(甲方A) | client_b(甲方B) | both(同时对接)')
    parser.add_argument('--http-url', type=str, default=None, help='覆盖 HTTP URL')
    parser.add_argument('--rtmp-url', type=str, default=None, help='覆盖 RTMP URL')
    parser.add_argument('--source', type=str, default=None, help='覆盖输入源，例如 0、视频路径、图片路径或 RTSP 地址')
    parser.add_argument('--raw-stream-only', action='store_true', help='只推送原始视频，跳过YOLO识别')
    parser.add_argument('--detect-stream', action='store_true', help='强制启用YOLO识别，覆盖预设中的纯推流模式')
    parser.add_argument('--auto-start', action='store_true', help='启动窗口后自动开始检测')
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
    if args.source:
        CONFIG["SOURCE"] = args.source
    if args.raw_stream_only:
        CONFIG["RAW_STREAM_ONLY"] = True
    if args.detect_stream:
        CONFIG["RAW_STREAM_ONLY"] = False

    app = QApplication(sys.argv)
    # 将配置好的 CONFIG 字典传给主窗口
    win = MainWindow(config=CONFIG)
    win.show()

    # 默认不自动启动，避免 Windows 上没有摄像头时反复触发 Camera Error 0
    if args.auto_start:
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(1000, win.run_or_continue)

    sys.exit(app.exec_())
