"""
果园机器人UDP客户端
模拟机器人发送数据
"""

import socket
import time
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from transport.robot_protocol import RobotProtocol

BEIJING_TIME = timezone(timedelta(hours=8), name="UTC+8")

# Windows 控制台默认可能是 GBK，统一改成 UTF-8，避免中文/符号输出报错
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

class RobotSimulator:
    """模拟果园机器人"""
    
    def __init__(
        self,
        robot_id: int = 1,
        robot_status: int = 1,
        server_host='1.14.205.24',
        server_port=4926,
        tree_interval_frames: int = 8,
        tree_interval_jitter: int = 2,
    ):
        """
        初始化机器人模拟器
        
        参数:
            robot_id: 机器人ID (1-255, 1=robotA, 2=robotB, 3=robotC)
            robot_status: 机器人状态 (0=关机,1=巡检,2=充电,255=故障)
            server_host: 服务器地址
            server_port: 服务器端口
            tree_interval_frames: 两次检测到果树之间的基础帧间隔
            tree_interval_jitter: 果树检测间隔允许的小范围波动
        """
        self.robot_id = robot_id
        self.robot_status = robot_status
        self.server_host = server_host
        self.server_port = server_port
        
        # 机器人状态
        self.frame_index = 0          # 帧计数（每秒+1）
        
        # 果树编号（新协议：拆分左右两路）
        self.left_tree_index = 0      # 左侧果树编号
        self.right_tree_index = 0     # 右侧果树编号
        
        # GPS位置（模拟北京附近：北纬39.9°, 东经116.4°）
        self.lat_decimal = 39.9 + random.uniform(-0.1, 0.1)
        self.lon_decimal = 116.4 + random.uniform(-0.1, 0.1)
        
        # 运动状态
        self.azimuth = random.randint(0, 359)      # 方位角（度，双字节存储）
        self.velocity = 10                          # 速度（单位：0.1m/s，0-100）
        self.eyepoint_height = 150                  # 摄像机高度（单位：0.01m，即1.5m）
        
        # 电源状态
        self.bat_voltage = 240                      # 电池电压（单位：0.1V，即24.0V）
        self.soc = 100                              # 剩余电量（%）
        
        # NFC检测和拍照状态（适配新协议：左右树分别检测）
        self.is_near_tree = False                   # 是否靠近树（NFC检测到）
        self.photo_frames = 0                       # 当前树拍照帧数
        self.photo_frames_target = 5                # 每棵树拍照帧数（5秒）
        self.next_tree_number = 1                   # 下一个果树编号（循环）
        self.tree_interval_frames = max(1, int(tree_interval_frames))
        self.tree_interval_jitter = max(0, int(tree_interval_jitter))
        self.next_tree_frame = self._next_tree_frame_from(0)
        
        # 创建UDP socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # 状态名称映射
        robot_names = {1: 'robotA', 2: 'robotB', 3: 'robotC'}
        status_names = {0: '关机', 1: '巡检', 2: '充电', 255: '故障'}
        
        print("=" * 70)
        print("果园机器人模拟器已初始化（新28字节协议）")
        print("=" * 70)
        print(f"机器人ID: {self.robot_id} ({robot_names.get(self.robot_id, f'robot{self.robot_id}')})")
        print(f"运行状态: {self.robot_status} ({status_names.get(self.robot_status, '未知')})")  # 替换sensor_id打印
        print(f"初始GPS位置: 北纬 {self.lat_decimal:.6f}°, 东经 {self.lon_decimal:.6f}°")
        print(f"初始方位角: {self.azimuth}°")
        print(f"初始速度: {self.velocity * 0.1:.1f} m/s")
        print(f"服务器地址: {self.server_host}:{self.server_port}")
        print(f"果树检测间隔: 约 {self.tree_interval_frames} 帧，波动 ±{self.tree_interval_jitter} 帧")
        print("=" * 70)
        print(f"工作模式: 自动巡航 -> 按间隔检测到树 -> 停留拍照 -> 继续移动")
        print("=" * 70)
        print()

    def _next_tree_frame_from(self, current_frame: int) -> int:
        """计算下一次检测到果树的帧号，间隔在小范围内波动。"""
        jitter = random.randint(-self.tree_interval_jitter, self.tree_interval_jitter)
        interval = max(1, self.tree_interval_frames + jitter)
        return int(current_frame + interval)
    
    def update_state(self):
        """更新机器人状态（适配新协议）"""
        # 更新帧计数（循环0-65535）
        self.frame_index = (self.frame_index + 1) % 65536
        
        # 模拟NFC检测和拍照流程（适配左右树）
        if not self.is_near_tree:
            # 状态1: 移动中，未检测到树
            self.left_tree_index = 0   # 无树时置0
            self.right_tree_index = 0  # 无树时置0
            
            # 按固定周期附带小幅波动，模拟每隔一段时间检测到一组果树
            if self.frame_index >= self.next_tree_frame:
                # NFC检测到树，左右树编号相邻
                self.is_near_tree = True
                self.left_tree_index = self.next_tree_number
                self.right_tree_index = self.next_tree_number + 1  # 右树编号=左树+1
                self.photo_frames = 0
                self.velocity = 0  # 停止移动
                print(f"  🌳 NFC检测到果树 | 左#{self.left_tree_index} | 右#{self.right_tree_index}，开始拍照")
            else:
                # 继续移动（故障状态下强制停止）
                if self.robot_status == 255:
                    self.velocity = 0  # 故障时停止移动
                else:
                    self.velocity = 10  # 保持移动速度 1.0 m/s
        else:
            # 状态2: 靠近树，正在拍照
            self.photo_frames += 1
            self.velocity = 0  # 停止不动
            
            # 左右树编号保持不变（持续拍照）
            if self.photo_frames >= self.photo_frames_target:
                # 拍照完成，离开这棵树
                print(f"  📸 果树拍照完成 | 左#{self.left_tree_index} | 右#{self.right_tree_index} ({self.photo_frames} 帧)")
                self.is_near_tree = False
                self.left_tree_index = 0
                self.right_tree_index = 0
                self.next_tree_number = (self.next_tree_number + 2) % 65536  # 下一组树编号（+2）
                self.next_tree_frame = self._next_tree_frame_from(self.frame_index)
                if self.robot_status != 255:  # 非故障状态恢复移动
                    self.velocity = 10
        
        # 模拟GPS位置变化
        if self.velocity > 0:
            # 移动时GPS变化
            self.lat_decimal += random.uniform(-0.0001, 0.0001)
            self.lon_decimal += random.uniform(-0.0001, 0.0001)
        else:
            # 静止时轻微漂移
            self.lat_decimal += random.uniform(-0.00001, 0.00001)
            self.lon_decimal += random.uniform(-0.00001, 0.00001)
        
        # 模拟方位角变化（0-359循环）
        if self.velocity > 0 and self.robot_status != 255:
            self.azimuth = (self.azimuth + random.randint(-10, 10)) % 360
        
        # 模拟摄像机高度变化（1.4m - 1.6m，范围0-255）
        self.eyepoint_height = min(255, 140 + random.randint(0, 20))
        
        # 模拟电池消耗（每帧消耗0.1%，故障状态下消耗更快）
        consume_rate = 0.2 if self.robot_status == 255 else 0.1
        self.soc = max(0, self.soc - consume_rate)
        
        # 电压随电量下降（20.0V - 24.0V）
        if self.soc < 95:
            self.bat_voltage = int(200 + (self.soc / 100) * 40)
        
        # 低电量警告
        if int(self.soc) in [20, 10, 5] and self.frame_index % 10 == 0:
            print(f"  ⚠️ 警告: 电量低 ({int(self.soc)}%)")
        
        # 充电状态下电量恢复
        if self.robot_status == 2:
            self.soc = min(100, self.soc + 0.5)
            self.bat_voltage = min(240, self.bat_voltage + 1)
            self.velocity = 0  # 充电时停止移动

    def send_data(self):
        """发送数据包（适配新28字节协议）"""
        # 获取当前时间
        now = datetime.now(BEIJING_TIME)
        hour = now.hour
        minute = now.minute
        second = now.second
        
        # 转换GPS坐标为度分秒
        lat_deg, lat_min, lat_sec, lat_dir = RobotProtocol.decimal_to_dms(
            self.lat_decimal, is_latitude=True
        )
        lon_deg, lon_min, lon_sec, lon_dir = RobotProtocol.decimal_to_dms(
            self.lon_decimal, is_latitude=False
        )
        
        # 确保所有值在新协议限定范围内
        azimuth = int(max(0, min(359, self.azimuth)))
        velocity = int(max(0, min(100, self.velocity)))  # 新协议限定0-100
        eyepoint_height = int(max(0, min(255, self.eyepoint_height)))
        bat_voltage = int(max(0, min(255, self.bat_voltage)))
        soc = int(max(0, min(100, self.soc)))
        
        # 确保果树编号和帧计数在16位范围内（0-65535）
        left_tree_safe = int(self.left_tree_index % 65536)
        right_tree_safe = int(self.right_tree_index % 65536)
        frame_index_safe = int(self.frame_index % 65536)
        
        # 打包数据（适配新协议的pack_robot_data参数）
        packet = RobotProtocol.pack_robot_data(
            robot_id=self.robot_id,
            robot_status=self.robot_status,  # 替换原sensor_id参数
            frame_index=frame_index_safe,
            left_tree_index=left_tree_safe,  # 新增左树编号
            right_tree_index=right_tree_safe, # 新增右树编号
            hour=hour,
            minute=minute,
            second=second,
            lat_degree=lat_deg,
            lat_minute=lat_min,
            lat_second=lat_sec,
            lat_direction=lat_dir,
            lon_degree=lon_deg,
            lon_minute=lon_min,
            lon_second=lon_sec,
            lon_direction=lon_dir,
            azimuth=azimuth,
            velocity=velocity,
            eyepoint_height=eyepoint_height,
            bat_voltage=bat_voltage,
            soc=soc
        )
        
        # 发送数据
        self.socket.sendto(packet, (self.server_host, self.server_port))
        
        # 显示发送信息（适配新协议）
        status_text = {0: "🔴关机", 1: "🟢巡检", 2: "🟡充电", 255: "🔴故障"}.get(self.robot_status, "❓未知")
        move_status = "📸拍照" if self.is_near_tree else "🚶移动"
        tree_info = f"左#{self.left_tree_index:3d} 右#{self.right_tree_index:3d}" if self.is_near_tree else "无树      "
        
        print(f"[UTC+8 {now.strftime('%H:%M:%S')}] {status_text} | 帧#{self.frame_index:5d} | "
              f"{move_status} | {tree_info} | "
              f"速度{self.velocity*0.1:.1f}m/s | "
              f"方位{self.azimuth:3d}° | "
              f"电量{int(self.soc):3d}%")
    
    def run(self, duration: float = None, interval: float = 1.0):
        """
        运行机器人模拟
        
        参数:
            duration: 运行时长（秒），None表示运行到电量耗尽
            interval: 发送间隔（秒，默认1秒）
        """
        # 故障状态提示
        if self.robot_status == 255:
            print("⚠️  机器人处于故障状态，将停止移动并快速消耗电量！\n")
        # 充电状态提示
        elif self.robot_status == 2:
            print("🔌 机器人处于充电状态，电量将持续恢复！\n")
        
        if duration is None:
            print(f"开始运行 (运行模式: 直到电量耗尽, 发送间隔: {interval}秒)\n")
        else:
            print(f"开始运行 (运行时长: {duration}秒, 发送间隔: {interval}秒)\n")
        
        start_time = time.time()
        trees_photographed = 0
        
        try:
            while True:
                # 检查运行时长
                if duration is not None and time.time() - start_time >= duration:
                    print(f"\n⏰ 达到设定运行时长")
                    break
                
                # 检查电量（故障状态下电量耗尽更快）
                if self.soc <= 0:
                    print(f"\n🔋 电量耗尽，机器人停止运行")
                    break
                
                # 更新状态
                prev_near_tree = self.is_near_tree
                self.update_state()
                
                # 统计拍摄的树数量
                if self.is_near_tree and not prev_near_tree:
                    trees_photographed += 1
                
                # 发送数据
                self.send_data()
                
                # 等待下一次发送
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print(f"\n⌨️  收到中断信号")
        
        # 显示统计（适配新协议）
        elapsed_time = time.time() - start_time
        print(f"\n" + "=" * 70)
        print(f"运行统计:")
        print(f"  运行时长: {elapsed_time:.1f} 秒")
        print(f"  总发送帧数: {self.frame_index}")
        print(f"  拍摄果树组数: {trees_photographed}")
        print(f"  剩余电量: {int(self.soc)}%")
        print(f"  当前电压: {self.bat_voltage * 0.1:.1f}V")
        print(f"  最终状态: {self.robot_status} ({['关机','巡检','充电','未知','故障'][min(self.robot_status,4)]})")
        print("=" * 70)
        
        self.socket.close()

def main():
    """主函数（适配新协议命令行参数）"""
    # 命令行参数:
    # [robot_id] [robot_status] [server_host] [server_port] [duration] [interval] [tree_interval] [tree_jitter]
    robot_id = 1
    robot_status = 1  # 默认巡检状态
    server_host = '1.14.205.24'
    server_port = 4926
    duration = None
    interval = 1.0
    tree_interval_frames = 8
    tree_interval_jitter = 2
    
    # 解析命令行参数（替换sensor_id为robot_status）
    if len(sys.argv) > 1:
        robot_id = int(sys.argv[1])
    if len(sys.argv) > 2:
        robot_status = int(sys.argv[2])  # 原sys.argv[2]是sensor_id，现在改为robot_status
    if len(sys.argv) > 3:
        server_host = sys.argv[3]
    if len(sys.argv) > 4:
        server_port = int(sys.argv[4])
    if len(sys.argv) > 5:
        duration_arg = float(sys.argv[5])
        duration = duration_arg if duration_arg > 0 else None
    if len(sys.argv) > 6:
        interval = float(sys.argv[6])
    if len(sys.argv) > 7:
        tree_interval_frames = int(sys.argv[7])
    if len(sys.argv) > 8:
        tree_interval_jitter = int(sys.argv[8])
    
    # 创建并运行机器人模拟器
    robot = RobotSimulator(
        robot_id,
        robot_status,
        server_host,
        server_port,
        tree_interval_frames=tree_interval_frames,
        tree_interval_jitter=tree_interval_jitter,
    )
    robot.run(duration=duration, interval=interval)

if __name__ == '__main__':
    main()
