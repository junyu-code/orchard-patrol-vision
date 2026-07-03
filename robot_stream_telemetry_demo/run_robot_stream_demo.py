#!/usr/bin/env python3
"""
独立联调程序。

功能：
1. 读取摄像头、视频文件或网络视频流。
2. 将原始视频帧缩放后推送到 RTMP。
3. 同时按 UDP 协议发送机器人状态、GPS、左右果树编号、电量等数据。
"""

import argparse
import math
import random
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

cv2 = None
np = None


def load_runtime_dependencies():
    """运行前再加载视频依赖，避免 --help 也被缺少 cv2 阻塞。"""
    global cv2, np
    if cv2 is not None and np is not None:
        return
    try:
        import cv2 as cv2_module
        import numpy as np_module
    except ModuleNotFoundError as exc:
        missing = exc.name
        raise RuntimeError(
            f"缺少依赖 {missing}，请先执行: pip install -r requirements.txt"
        ) from exc
    cv2 = cv2_module
    np = np_module


class RobotProtocol:
    """机器人遥测 28 字节 UDP 二进制协议。"""

    SEND_HEAD = 0x66
    SEND_TAIL = 0x99
    PACKET_SIZE = 28

    LAT_NORTH = 0x4E  # N
    LAT_SOUTH = 0x53  # S
    LON_EAST = 0x45   # E
    LON_WEST = 0x57   # W

    @staticmethod
    def clamp(value, low, high):
        return int(max(low, min(high, value)))

    @staticmethod
    def decimal_to_dms(decimal_value, is_latitude=True):
        """十进制度转协议里的度、分、秒、方向。"""
        direction = RobotProtocol.LAT_NORTH if is_latitude else RobotProtocol.LON_EAST
        if decimal_value < 0:
            direction = RobotProtocol.LAT_SOUTH if is_latitude else RobotProtocol.LON_WEST

        total_seconds = int(round(abs(float(decimal_value)) * 3600))
        degree = total_seconds // 3600
        minute = (total_seconds % 3600) // 60
        second = total_seconds % 60
        return degree, minute, second, direction

    @staticmethod
    def pack_robot_data(
        robot_id,
        robot_status,
        frame_index,
        left_tree_code,
        right_tree_code,
        hour,
        minute,
        second,
        lat_degree,
        lat_minute,
        lat_second,
        lat_direction,
        lon_degree,
        lon_minute,
        lon_second,
        lon_direction,
        azimuth,
        velocity,
        eye_point_height,
        bat_voltage,
        soc,
    ):
        """打包固定 28 字节协议包。"""
        robot_id = RobotProtocol.clamp(robot_id, 0, 255)
        robot_status = RobotProtocol.clamp(robot_status, 0, 255)
        frame_index = RobotProtocol.clamp(frame_index, 0, 65535)
        left_tree_code = RobotProtocol.clamp(left_tree_code, 0, 65535)
        right_tree_code = RobotProtocol.clamp(right_tree_code, 0, 65535)
        hour = RobotProtocol.clamp(hour, 0, 23)
        minute = RobotProtocol.clamp(minute, 0, 59)
        second = RobotProtocol.clamp(second, 0, 59)
        lat_degree = RobotProtocol.clamp(lat_degree, 0, 90)
        lat_minute = RobotProtocol.clamp(lat_minute, 0, 59)
        lat_second = RobotProtocol.clamp(lat_second, 0, 59)
        lon_degree = RobotProtocol.clamp(lon_degree, 0, 180)
        lon_minute = RobotProtocol.clamp(lon_minute, 0, 59)
        lon_second = RobotProtocol.clamp(lon_second, 0, 59)
        azimuth = RobotProtocol.clamp(azimuth, 0, 65535)
        velocity = RobotProtocol.clamp(velocity, 0, 255)
        eye_point_height = RobotProtocol.clamp(eye_point_height, 0, 255)
        bat_voltage = RobotProtocol.clamp(bat_voltage, 0, 255)
        soc = RobotProtocol.clamp(soc, 0, 100)

        if lat_direction not in (RobotProtocol.LAT_NORTH, RobotProtocol.LAT_SOUTH):
            lat_direction = RobotProtocol.LAT_NORTH
        if lon_direction not in (RobotProtocol.LON_EAST, RobotProtocol.LON_WEST):
            lon_direction = RobotProtocol.LON_EAST

        data_bytes = [
            robot_id,
            robot_status,
            (frame_index >> 8) & 0xFF,
            frame_index & 0xFF,
            (left_tree_code >> 8) & 0xFF,
            left_tree_code & 0xFF,
            (right_tree_code >> 8) & 0xFF,
            right_tree_code & 0xFF,
            hour,
            minute,
            second,
            lat_degree,
            lat_minute,
            lat_second,
            lat_direction,
            lon_degree,
            lon_minute,
            lon_second,
            lon_direction,
            (azimuth >> 8) & 0xFF,
            azimuth & 0xFF,
            velocity,
            eye_point_height,
            bat_voltage,
            soc,
        ]
        checksum = sum(data_bytes) & 0xFF
        return bytes([RobotProtocol.SEND_HEAD] + data_bytes + [checksum, RobotProtocol.SEND_TAIL])


class RtmpSender:
    """通过 FFmpeg 将 OpenCV BGR 帧推送到 RTMP。"""

    def __init__(self, rtmp_url, video_bitrate, maxrate, bufsize, preset="veryfast"):
        self.rtmp_url = rtmp_url
        self.video_bitrate = video_bitrate
        self.maxrate = maxrate
        self.bufsize = bufsize
        self.preset = preset
        self.process = None
        self.is_running = False

    def start(self, width, height, fps):
        if self.is_running:
            return

        command = [
            "ffmpeg",
            "-y",
            "-loglevel", "error",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{width}x{height}",
            "-pix_fmt", "bgr24",
            "-r", str(fps),
            "-i", "-",
            "-an",
            "-vcodec", "libx264",
            "-preset", self.preset,
            "-tune", "zerolatency",
            "-pix_fmt", "yuv420p",
            "-b:v", self.video_bitrate,
            "-maxrate", self.maxrate,
            "-bufsize", self.bufsize,
            "-g", str(max(1, int(fps) * 2)),
            "-f", "flv",
            self.rtmp_url,
        ]

        try:
            self.process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            self.is_running = True
            print(f"RTMP 已启动: {width}x{height}@{fps}fps, bitrate={self.video_bitrate}")
            print(f"RTMP 地址: {self.rtmp_url}")
        except FileNotFoundError:
            print("错误: 未找到 ffmpeg，请先安装 FFmpeg 并加入 PATH。")
            self.is_running = False

    def send_frame(self, frame):
        if not self.is_running or self.process is None or self.process.stdin is None:
            return False
        try:
            self.process.stdin.write(frame.tobytes())
            return True
        except BrokenPipeError:
            print("RTMP 推流断开: BrokenPipe")
            self.stop()
            return False

    def stop(self):
        if not self.process:
            return
        try:
            if self.process.stdin:
                self.process.stdin.close()
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
        finally:
            self.process = None
            self.is_running = False
            print("RTMP 已停止")


class VirtualSensor:
    """模拟 GPS、速度、方位角、电量等机器人状态。"""

    def __init__(self, latitude=25.28, longitude=110.34):
        self.latitude = float(latitude)
        self.longitude = float(longitude)
        self.azimuth = 14
        self.velocity = 0.8
        self.eye_point_height = 1.57
        self.bat_voltage = 24.0
        self.soc = 98.0
        self.last_update_time = time.time()

    def update(self, is_near_tree=False):
        now = time.time()
        elapsed = max(0.05, min(2.0, now - self.last_update_time))
        self.last_update_time = now

        if is_near_tree:
            self.velocity = 0.0
            self.latitude += random.uniform(-0.000001, 0.000001)
            self.longitude += random.uniform(-0.000001, 0.000001)
        else:
            self.velocity = max(0.4, min(1.2, self.velocity + random.uniform(-0.04, 0.04)))
            rad = math.radians(self.azimuth)
            meters_per_degree = 111320.0
            distance = self.velocity * elapsed
            self.latitude += math.cos(rad) * distance / meters_per_degree
            lon_scale = max(0.2, math.cos(math.radians(self.latitude)))
            self.longitude += math.sin(rad) * distance / (meters_per_degree * lon_scale)
            self.azimuth = (self.azimuth + random.randint(-3, 3)) % 360

        self.eye_point_height = random.uniform(1.50, 1.60)
        self.soc = max(0.0, self.soc - 0.002 * elapsed)
        self.bat_voltage = 20.0 + (self.soc / 100.0) * 4.0

    def gps_dms(self):
        lat = RobotProtocol.decimal_to_dms(self.latitude, is_latitude=True)
        lon = RobotProtocol.decimal_to_dms(self.longitude, is_latitude=False)
        return lat + lon

    def protocol_status(self):
        return {
            "azimuth": int(round(self.azimuth)),
            "velocity": int(round(self.velocity * 10)),              # 1LSB = 0.1m/s
            "eye_point_height": int(round(self.eye_point_height * 100)),  # 1LSB = 0.01m
            "bat_voltage": int(round(self.bat_voltage * 10)),        # 1LSB = 0.1V
            "soc": int(round(self.soc)),
        }


class PatrolTimeline:
    """按视频播放时间触发左右果树编号。"""

    def __init__(self, event_times, start_tree_code=1, tolerance=0.08):
        self.event_times = sorted(float(item) for item in event_times)
        self.next_tree_code = int(start_tree_code)
        self.tolerance = float(tolerance)
        self.last_time_by_turn = {}
        self.triggered = set()

    def consume(self, playback_time, direction=1, traversal_index=0):
        if playback_time is None or not self.event_times:
            return None

        playback_time = float(playback_time)
        direction = 1 if int(direction or 1) >= 0 else -1
        traversal_index = int(traversal_index or 0)
        key = (traversal_index, direction)
        previous_time = self.last_time_by_turn.get(key)
        self.last_time_by_turn[key] = playback_time

        matched_time = self._matched_time(previous_time, playback_time, direction)
        if matched_time is None:
            return None

        event_key = (traversal_index, direction, matched_time)
        if event_key in self.triggered:
            return None
        self.triggered.add(event_key)

        left_code = self.next_tree_code
        right_code = self.next_tree_code + 1
        self.next_tree_code += 2
        if self.next_tree_code > 65535:
            self.next_tree_code = 1

        return {
            "left_tree_code": left_code,
            "right_tree_code": right_code,
            "event_time": matched_time,
        }

    def _matched_time(self, previous_time, current_time, direction):
        if previous_time is None:
            for event_time in self.event_times:
                if abs(current_time - event_time) <= self.tolerance:
                    return event_time
            return None

        if direction >= 0:
            for event_time in self.event_times:
                if previous_time < event_time <= current_time:
                    return event_time
        else:
            for event_time in reversed(self.event_times):
                if current_time <= event_time < previous_time:
                    return event_time
        return None


class UdpSender:
    """发送机器人 UDP 遥测数据。"""

    def __init__(self, host, port, robot_id, orchard_code="orchard1", add_orchard_prefix=True):
        self.host = host
        self.port = int(port)
        self.robot_id = int(robot_id)
        self.orchard_code = str(orchard_code)
        self.add_orchard_prefix = bool(add_orchard_prefix)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.left_tree_code = 0
        self.right_tree_code = 0

    def send(self, frame_index, sensor, tree_event=None):
        now = datetime.now()
        if tree_event:
            self.left_tree_code = int(tree_event["left_tree_code"])
            self.right_tree_code = int(tree_event["right_tree_code"])
        else:
            self.left_tree_code = 0
            self.right_tree_code = 0

        sensor.update(is_near_tree=bool(tree_event))
        lat_d, lat_m, lat_s, lat_dir, lon_d, lon_m, lon_s, lon_dir = sensor.gps_dms()
        status = sensor.protocol_status()

        robot_status = 1 if tree_event else 0
        raw_packet = RobotProtocol.pack_robot_data(
            robot_id=self.robot_id,
            robot_status=robot_status,
            frame_index=frame_index % 65536,
            left_tree_code=self.left_tree_code,
            right_tree_code=self.right_tree_code,
            hour=now.hour,
            minute=now.minute,
            second=now.second,
            lat_degree=lat_d,
            lat_minute=lat_m,
            lat_second=lat_s,
            lat_direction=lat_dir,
            lon_degree=lon_d,
            lon_minute=lon_m,
            lon_second=lon_s,
            lon_direction=lon_dir,
            azimuth=status["azimuth"],
            velocity=status["velocity"],
            eye_point_height=status["eye_point_height"],
            bat_voltage=status["bat_voltage"],
            soc=status["soc"],
        )

        packet = raw_packet
        if self.add_orchard_prefix:
            packet = f"{self.orchard_code}|".encode("utf-8") + raw_packet

        self.sock.sendto(packet, (self.host, self.port))
        return {
            "length": len(packet),
            "robot_status": robot_status,
            "left_tree_code": self.left_tree_code,
            "right_tree_code": self.right_tree_code,
            "latitude": sensor.latitude,
            "longitude": sensor.longitude,
            "azimuth": status["azimuth"],
            "velocity": status["velocity"] / 10.0,
            "soc": status["soc"],
        }

    def close(self):
        self.sock.close()


class RawFrameReader:
    """只读取原始帧，不做 YOLO 预处理。"""

    def __init__(self, source, loop=True, pingpong=True):
        self.source = str(source)
        self.loop = bool(loop)
        self.pingpong = bool(pingpong)
        self.direction = 1
        self.traversal_index = 0
        self.reverse_index = None

        capture_source = int(self.source) if self.source.isnumeric() else self.source
        if self.source.isnumeric() and sys.platform.startswith("win"):
            self.cap = cv2.VideoCapture(capture_source, cv2.CAP_DSHOW)
            if not self.cap.isOpened():
                self.cap = cv2.VideoCapture(capture_source)
        else:
            self.cap = cv2.VideoCapture(capture_source)

        if not self.cap.isOpened():
            raise RuntimeError(f"无法打开视频源: {self.source}")

        self.fps = float(self.cap.get(cv2.CAP_PROP_FPS) or 25.0)
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        self.last_frame = max(0, self.frame_count - 1)

    def read(self):
        if self.direction < 0:
            ok, frame = self._read_reverse()
        else:
            ok, frame = self.cap.read()
            if not ok:
                ok, frame = self._handle_end()

        if not ok or frame is None:
            return None, None, None, None

        pos_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES) or 1) - 1
        if self.direction < 0 and self.reverse_index is not None:
            source_frame = max(0, min(self.last_frame, self.reverse_index + 1))
        else:
            source_frame = max(0, pos_frame)

        playback_time = source_frame / max(self.fps, 1.0)
        return frame, playback_time, self.direction, self.traversal_index

    def _handle_end(self):
        if not self.loop:
            return False, None

        if self.pingpong and self.frame_count > 1:
            self.direction *= -1
            self.traversal_index += 1
            if self.direction < 0:
                self.reverse_index = self.last_frame
                return self._read_reverse()

        self.direction = 1
        self.reverse_index = None
        self.traversal_index += 1
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        return self.cap.read()

    def _read_reverse(self):
        if self.reverse_index is None:
            self.reverse_index = self.last_frame
        if self.reverse_index < 0:
            return self._handle_end()

        self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.reverse_index)
        ok, frame = self.cap.read()
        self.reverse_index -= 1
        return ok, frame

    def close(self):
        self.cap.release()


def parse_tree_times(text):
    if not text.strip():
        return []
    return [float(item.strip()) for item in text.split(",") if item.strip()]


def even(value):
    value = int(value)
    return value - (value % 2)


def resolve_source_path(source):
    """相对路径按脚本所在目录解析，方便整包复制后直接运行。"""
    source = str(source)
    if source.isnumeric() or source.lower().startswith(("rtsp://", "rtmp://", "http://", "https://")):
        return source
    path = Path(source)
    if path.is_absolute():
        return str(path)
    return str(Path(__file__).resolve().parent / path)


def parse_args():
    parser = argparse.ArgumentParser(description="视频流与机器人遥测独立联调程序")
    parser.add_argument("--source", default="media/patrol_demo.mp4", help="视频源：摄像头编号、视频文件、RTSP/RTMP/HTTP 地址")
    parser.add_argument("--rtmp-url", default="rtmp://www.xsjny.com/live/robot1_sensor1", help="RTMP 推流地址")
    parser.add_argument("--udp-host", default="1.15.149.164", help="UDP 接收地址")
    parser.add_argument("--udp-port", type=int, default=4926, help="UDP 接收端口")
    parser.add_argument("--orchard-code", default="orchard1", help="果园编号前缀")
    parser.add_argument("--no-orchard-prefix", action="store_true", help="只发送裸 28 字节 UDP 包")
    parser.add_argument("--robot-id", type=int, default=1, help="机器人编号")
    parser.add_argument("--latitude", type=float, default=25.28, help="模拟 GPS 纬度")
    parser.add_argument("--longitude", type=float, default=110.34, help="模拟 GPS 经度")
    parser.add_argument("--max-width", type=int, default=480, help="RTMP 最大推流宽度")
    parser.add_argument("--fps", type=int, default=10, help="RTMP 推流帧率")
    parser.add_argument("--bitrate", default="400k", help="RTMP 视频码率")
    parser.add_argument("--maxrate", default="550k", help="RTMP 峰值码率")
    parser.add_argument("--bufsize", default="800k", help="RTMP 编码缓冲区")
    parser.add_argument("--udp-interval", type=float, default=1.0, help="UDP 心跳间隔，单位秒")
    parser.add_argument("--tree-times", default="1,5,9,13,17,22,27,31,35,39", help="果树事件触发秒点，逗号分隔；空字符串表示不触发")
    parser.add_argument("--start-tree-code", type=int, default=1, help="起始果树编号")
    parser.add_argument("--duration", type=float, default=0, help="运行时长，0 表示一直运行")
    parser.add_argument("--no-loop", action="store_true", help="视频文件播放到末尾后退出")
    parser.add_argument("--no-pingpong", action="store_true", help="视频文件不倒放循环，只从头重播")
    return parser.parse_args()


def main():
    args = parse_args()
    load_runtime_dependencies()
    reader = RawFrameReader(
        resolve_source_path(args.source),
        loop=not args.no_loop,
        pingpong=not args.no_pingpong,
    )
    sensor = VirtualSensor(latitude=args.latitude, longitude=args.longitude)
    udp_sender = UdpSender(
        host=args.udp_host,
        port=args.udp_port,
        robot_id=args.robot_id,
        orchard_code=args.orchard_code,
        add_orchard_prefix=not args.no_orchard_prefix,
    )
    timeline = PatrolTimeline(
        event_times=parse_tree_times(args.tree_times),
        start_tree_code=args.start_tree_code,
    )
    rtmp_sender = None

    first_frame, playback_time, direction, traversal_index = reader.read()
    if first_frame is None:
        raise RuntimeError("视频源没有读取到画面")

    height, width = first_frame.shape[:2]
    if width > args.max_width:
        ratio = args.max_width / width
        push_width = even(args.max_width)
        push_height = even(height * ratio)
    else:
        push_width = even(width)
        push_height = even(height)

    rtmp_sender = RtmpSender(
        rtmp_url=args.rtmp_url,
        video_bitrate=args.bitrate,
        maxrate=args.maxrate,
        bufsize=args.bufsize,
    )
    rtmp_sender.start(push_width, push_height, args.fps)

    print("视频流与机器人遥测联调程序已启动")
    print(f"视频源: {args.source}")
    print(f"UDP: {args.udp_host}:{args.udp_port}")
    print(f"UDP 格式: {'28字节裸包' if args.no_orchard_prefix else args.orchard_code + '| + 28字节包'}")
    print(f"GPS 起点: latitude={args.latitude}, longitude={args.longitude}")

    frame_index = 0
    last_udp_time = 0.0
    start_time = time.time()
    next_frame_time = start_time

    try:
        pending = (first_frame, playback_time, direction, traversal_index)
        while True:
            if args.duration > 0 and time.time() - start_time >= args.duration:
                break

            if pending:
                frame, playback_time, direction, traversal_index = pending
                pending = None
            else:
                frame, playback_time, direction, traversal_index = reader.read()
                if frame is None:
                    break

            frame_index += 1
            if frame.shape[1] != push_width or frame.shape[0] != push_height:
                push_frame = cv2.resize(frame, (push_width, push_height))
            else:
                push_frame = frame
            push_frame = np.ascontiguousarray(push_frame)
            rtmp_sender.send_frame(push_frame)

            tree_event = timeline.consume(
                playback_time=playback_time,
                direction=direction,
                traversal_index=traversal_index,
            )
            now = time.time()
            should_send_udp = bool(tree_event) or (now - last_udp_time >= args.udp_interval)
            if should_send_udp:
                summary = udp_sender.send(frame_index, sensor, tree_event=tree_event)
                last_udp_time = now
                print(
                    f"UDP 已发送 | frame={frame_index} | status={summary['robot_status']} | "
                    f"leftTreeCode={summary['left_tree_code']} rightTreeCode={summary['right_tree_code']} | "
                    f"GPS={summary['latitude']:.6f},{summary['longitude']:.6f} | "
                    f"speed={summary['velocity']:.1f}m/s | soc={summary['soc']}% | bytes={summary['length']}"
                )

            next_frame_time += 1.0 / max(1, args.fps)
            sleep_seconds = next_frame_time - time.time()
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
            else:
                next_frame_time = time.time()
    except KeyboardInterrupt:
        print("收到停止信号，正在退出...")
    finally:
        reader.close()
        udp_sender.close()
        if rtmp_sender:
            rtmp_sender.stop()


if __name__ == "__main__":
    main()
