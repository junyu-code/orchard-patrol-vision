"""
UDP 数据发送模块 - 用于向甲方B统一平台发送机器人数据
基于果园机器人UDP协议
"""

import socket
import time
import random
import sys
from datetime import datetime
from .robot_protocol import RobotProtocol

# Windows 控制台可能默认使用 GBK，统一输出编码避免中文和符号报错
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


class UdpSender:
    """UDP 数据发送器"""

    def __init__(self,
                 udp_host='1.15.149.164',
                 udp_port=4926,
                 robot_id=1,
                 sensor_id=1,
                 orchard_id='orchard1',
                 add_orchard_prefix=False,
                 simulate_tree_events=False,
                 tree_interval=8,
                 tree_jitter=2,
                 tree_hold_frames=5):
        """
        初始化 UDP 发送器

        参数:
            udp_host: UDP 服务器地址
            udp_port: UDP 服务器端口
            robot_id: 机器人ID (1=robot1, 2=robot2, 3=robot3)
            sensor_id: 传感器ID (当前未使用，预留)
            simulate_tree_events: 是否在无识别结果时按间隔模拟果树出现
            tree_interval: 模拟果树出现的基础发送间隔
            tree_jitter: 模拟果树出现间隔的允许波动
            tree_hold_frames: 每次检测到果树后保持编号的发送次数
        """
        self.udp_host = udp_host
        self.udp_port = udp_port
        self.robot_id = robot_id
        self.sensor_id = sensor_id
        self.orchard_id = str(orchard_id or '').strip()
        self.add_orchard_prefix = bool(add_orchard_prefix)
        self.simulate_tree_events = simulate_tree_events
        self.tree_interval = max(1, int(tree_interval))
        self.tree_jitter = max(0, int(tree_jitter))
        self.tree_hold_frames = max(1, int(tree_hold_frames))

        # 创建 UDP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # 果树计数（新协议：左右分开）
        self.left_tree_index = 0
        self.right_tree_index = 0
        self.next_tree_number = 1
        self.tree_hold_remaining = 0
        self.next_tree_frame = self._next_tree_frame_from(0)
        self.last_packet_data = None

        print(f"✅ UDP 发送器已初始化: {udp_host}:{udp_port} | Robot ID: {robot_id}")
        if self.add_orchard_prefix:
            print(f"   UDP中央平台格式: {self.orchard_id}| + 28字节机器人协议包")
        if self.simulate_tree_events:
            print(
                f"   果树模拟: 每 {self.tree_interval}±{self.tree_jitter} 次发送出现一组，"
                f"保持 {self.tree_hold_frames} 次"
            )

    def _next_tree_frame_from(self, frame_index):
        """计算下一次模拟果树出现的帧号。"""
        jitter = random.randint(-self.tree_jitter, self.tree_jitter)
        return int(frame_index + max(1, self.tree_interval + jitter))

    def _update_tree_indices(self, frame_index, disease_detected, tree_event=None):
        """更新左右果树编号；协议要求无树时编号为 0。"""
        if tree_event:
            left_tree_id = int(tree_event.get("left_tree_id", tree_event.get("tree_id", self.next_tree_number)))
            right_tree_id = int(tree_event.get("right_tree_id", left_tree_id + 1))
            self.left_tree_index = max(0, min(65535, left_tree_id))
            self.right_tree_index = max(0, min(65535, right_tree_id))
            self.next_tree_number = max(self.next_tree_number, self.right_tree_index + 1)
            if self.next_tree_number > 65535:
                self.next_tree_number = 1
            self.tree_hold_remaining = 0
            self.next_tree_frame = self._next_tree_frame_from(frame_index)
            return

        if disease_detected:
            self.left_tree_index = self.next_tree_number
            self.right_tree_index = self.next_tree_number + 1
            self.next_tree_number = (self.next_tree_number + 2) % 65536
            self.tree_hold_remaining = 0
            self.next_tree_frame = self._next_tree_frame_from(frame_index)
            return

        if not self.simulate_tree_events:
            self.left_tree_index = 0
            self.right_tree_index = 0
            return

        if self.tree_hold_remaining > 0:
            self.tree_hold_remaining -= 1
            if self.tree_hold_remaining == 0:
                self.next_tree_frame = self._next_tree_frame_from(frame_index)
            return

        if frame_index >= self.next_tree_frame:
            self.left_tree_index = self.next_tree_number
            self.right_tree_index = self.next_tree_number + 1
            self.next_tree_number = (self.next_tree_number + 2) % 65536
            self.tree_hold_remaining = self.tree_hold_frames - 1
            return

        self.left_tree_index = 0
        self.right_tree_index = 0

    def send_robot_data(self,
                       robot_status=1,
                       frame_index=0,
                       lat_degree=39, lat_minute=54, lat_second=20, lat_direction='N',
                       lon_degree=116, lon_minute=23, lon_second=29, lon_direction='E',
                       azimuth=0,
                       velocity=0,
                       eyepoint_height=150,
                       bat_voltage=240,
                       soc=85,
                       disease_detected=False,
                       tree_event=None):
        """
        发送机器人数据

        参数:
            robot_status: 机器人状态 (0=关机, 1=巡检, 2=充电, 255=故障)
            frame_index: 帧索引
            lat_degree, lat_minute, lat_second, lat_direction: 纬度
            lon_degree, lon_minute, lon_second, lon_direction: 经度
            azimuth: 方向角 (0-359度)
            velocity: 速度 (单位: 0.1m/s, 例如 10 = 1.0m/s)
            eyepoint_height: 摄像头高度 (单位: 0.01m, 例如 150 = 1.5m)
            bat_voltage: 电池电压 (单位: 0.1V, 例如 240 = 24.0V)
            soc: 剩余电量 (0-100%)
            disease_detected: 是否检测到病害 (用于更新果树编号)
            tree_event: 甲方B演示时间轴触发的果树事件，格式为 {"tree_id": 1, "tree_code": "ID0001"}
        """
        try:
            # 获取当前时间
            now = datetime.now()
            hour = now.hour
            minute = now.minute
            second = now.second

            # 更新左右果树编号；甲方B固定巡检事件优先，其次才是识别结果或备用随机模拟
            self._update_tree_indices(frame_index, disease_detected, tree_event=tree_event)

            # 转换方向字符为协议码
            lat_dir_code = RobotProtocol.LAT_NORTH if lat_direction == 'N' else RobotProtocol.LAT_SOUTH
            lon_dir_code = RobotProtocol.LON_EAST if lon_direction == 'E' else RobotProtocol.LON_WEST

            # 打包数据
            packet = RobotProtocol.pack_robot_data(
                robot_id=self.robot_id,
                robot_status=robot_status,
                frame_index=frame_index,
                left_tree_index=self.left_tree_index,
                right_tree_index=self.right_tree_index,
                hour=hour,
                minute=minute,
                second=second,
                lat_degree=lat_degree,
                lat_minute=lat_minute,
                lat_second=lat_second,
                lat_direction=lat_dir_code,
                lon_degree=lon_degree,
                lon_minute=lon_minute,
                lon_second=lon_second,
                lon_direction=lon_dir_code,
                azimuth=azimuth,
                velocity=velocity,
                eyepoint_height=eyepoint_height,
                bat_voltage=bat_voltage,
                soc=soc
            )

            # 发送数据：直连中央平台时，模拟 relay/udp_forwarder.py 的 orchard_id| 前缀格式。
            send_packet = packet
            if self.add_orchard_prefix:
                send_packet = f"{self.orchard_id}|".encode("utf-8") + packet

            self.sock.sendto(send_packet, (self.udp_host, self.udp_port))
            self.last_packet_data = RobotProtocol.unpack_robot_data(packet)
            return True

        except Exception as e:
            print(f"❌ UDP 发送失败: {e}")
            return False

    def get_last_packet_summary(self):
        """返回最近一次 UDP 包的人类可读摘要，用于本地联调日志。"""
        if not self.last_packet_data:
            return ""

        data = self.last_packet_data
        gps = data["gps"]
        trees = data["tree_index"]
        status_text = "near_tree" if trees["left"] or trees["right"] else "moving"
        return (
            f"状态:{status_text} | "
            f"帧:{data['frame_index']} | "
            f"左树:ID{trees['left']:04d} 右树:ID{trees['right']:04d} | "
            f"GPS:{gps['latitude']['decimal']:.6f},{gps['longitude']['decimal']:.6f} | "
            f"方向:{data['azimuth']}° | "
            f"速度:{data['velocity']:.1f}m/s | "
            f"相机:{data['eyepoint_height']:.2f}m | "
            f"电压:{data['battery_voltage']:.1f}V | "
            f"电量:{data['soc']}%"
        )

    def close(self):
        """关闭 UDP socket"""
        try:
            self.sock.close()
            print("✅ UDP 连接已关闭")
        except:
            pass


if __name__ == "__main__":
    # 测试代码
    sender = UdpSender(udp_host='1.15.149.164', udp_port=4926, robot_id=1)

    print("开始发送测试数据...")
    for i in range(5):
        success = sender.send_robot_data(
            robot_status=1,
            frame_index=i,
            disease_detected=(i % 3 == 0)  # 每3帧检测到一次病害
        )
        if success:
            print(f"✅ 第 {i+1} 帧数据已发送")
        time.sleep(1)

    sender.close()
    print("测试完成")
