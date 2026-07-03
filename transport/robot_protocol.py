"""
果园机器人UDP通信协议定义
"""

import struct
import time
from typing import Dict, Tuple, Any

class RobotProtocol:
    """果园机器人UDP协议"""
    
    # 协议常量
    SEND_HEAD = 0x66  # 包头
    SEND_TAIL = 0x99  # 包尾
    PACKET_SIZE = 28  # 数据包总大小（字节）
    
    # GPS方向常量
    LAT_NORTH = 0x4E  # 'N' 北纬
    LAT_SOUTH = 0x53  # 'S' 南纬
    LON_EAST = 0x45   # 'E' 东经
    LON_WEST = 0x57   # 'W' 西经
    
    # 机器人ID常量（1~255）
    ROBOT_A = 1  # 机器人A
    ROBOT_B = 2  # 机器人B
    ROBOT_C = 3  # 机器人C
    
    # 机器人运行状态常量
    ROBOT_STATUS_SHUTDOWN = 0     # 关机/掉电/停止运行
    ROBOT_STATUS_PATROLLING = 1   # 正在巡检
    ROBOT_STATUS_CHARGING = 2     # 充电状态
    ROBOT_STATUS_FAULT = 255      # 故障需检修
    ROBOT_STATUS_UNKNOWN = -1     # 未知状态
    
    @staticmethod
    def pack_robot_data(
        robot_id: int,              # 机器人ID (1-255)
        robot_status: int,          # 机器人运行状态 (0-255，甲方B旧模拟中0=移动，1=靠近树/拍照)
        frame_index: int,           # 数据帧计数 (0-65535，每秒+1)
        left_tree_index: int,       # 左侧果树编号 (0-65535)
        right_tree_index: int,      # 右侧果树编号 (0-65535)
        hour: int,                  # 时钟值 (0-23)
        minute: int,                # 分钟值 (0-59)
        second: int,                # 秒钟值 (0-59)
        lat_degree: int,            # 纬度度数 (0-90)
        lat_minute: int,            # 纬度分数 (0-59)
        lat_second: int,            # 纬度秒数 (0-59)
        lat_direction: int,         # 纬度方向 (0x4E=N, 0x53=S)
        lon_degree: int,            # 经度度数 (0-180)
        lon_minute: int,            # 经度分数 (0-59)
        lon_second: int,            # 经度秒数 (0-59)
        lon_direction: int,         # 经度方向 (0x45=E, 0x57=W)
        azimuth: int,               # 行进方向 (0-359，双字节存储)
        velocity: int,              # 速度 (0-255, 1LSB=0.1m/s)
        eyepoint_height: int,       # 摄像机高度 (0-255, 1LSB=0.01m)
        bat_voltage: int,           # 电池电压 (0-255, 1LSB=0.1V)
        soc: int                    # 剩余电量 (0-100, 1%/LSB)
    ) -> bytes:
        """
        打包机器人数据
        
        返回:
            打包后的28字节数据
        """
        # ========== 1. 参数范围验证和类型转换 ==========
        robot_id = int(max(1, min(255, robot_id)))  # 范围1~255
        robot_status = int(max(0, min(255, robot_status)))
        frame_index = int(max(0, min(65535, frame_index)))
        left_tree_index = int(max(0, min(65535, left_tree_index)))
        right_tree_index = int(max(0, min(65535, right_tree_index)))
        hour = int(max(0, min(23, hour)))
        minute = int(max(0, min(59, minute)))
        second = int(max(0, min(59, second)))
        lat_degree = int(max(0, min(90, lat_degree)))
        lat_minute = int(max(0, min(59, lat_minute)))
        lat_second = int(max(0, min(59, lat_second)))
        
        # 验证纬度方向（必须是 N 或 S）
        if lat_direction not in [RobotProtocol.LAT_NORTH, RobotProtocol.LAT_SOUTH]:
            lat_direction = RobotProtocol.LAT_NORTH  # 默认北纬
        lat_direction = int(lat_direction)
        
        lon_degree = int(max(0, min(180, lon_degree)))
        lon_minute = int(max(0, min(59, lon_minute)))
        lon_second = int(max(0, min(59, lon_second)))
        
        # 验证经度方向（必须是 E 或 W）
        if lon_direction not in [RobotProtocol.LON_EAST, RobotProtocol.LON_WEST]:
            lon_direction = RobotProtocol.LON_EAST  # 默认东经
        lon_direction = int(lon_direction)
        
        azimuth = int(max(0, min(359, azimuth)))  # 范围0~359
        velocity = int(max(0, min(255, velocity)))
        eyepoint_height = int(max(0, min(255, eyepoint_height)))
        bat_voltage = int(max(0, min(255, bat_voltage)))
        soc = int(max(0, min(100, soc)))
        
        # ========== 2. 拆分16位数据为高低字节 ==========
        frame_index_h = (frame_index >> 8) & 0xFF
        frame_index_l = frame_index & 0xFF
        left_tree_index_h = (left_tree_index >> 8) & 0xFF
        left_tree_index_l = left_tree_index & 0xFF
        right_tree_index_h = (right_tree_index >> 8) & 0xFF
        right_tree_index_l = right_tree_index & 0xFF
        azimuth_h = (azimuth >> 8) & 0xFF  # 方位角高八位（仅0/1）
        azimuth_l = azimuth & 0xFF         # 方位角低八位
        
        # ========== 3. 构建核心数据段 ==========
        data_bytes = [
            robot_id,                # 1: 机器人ID
            robot_status,            # 2: 机器人状态
            frame_index_h,           # 3: 帧计数高八位
            frame_index_l,           # 4: 帧计数低八位
            left_tree_index_h,       # 5: 左果树编号高八位
            left_tree_index_l,       # 6: 左果树编号低八位
            right_tree_index_h,      # 7: 右果树编号高八位
            right_tree_index_l,      # 8: 右果树编号低八位
            hour,                    # 9: 小时
            minute,                  # 10: 分钟
            second,                  # 11: 秒
            lat_degree,              # 12: 纬度度
            lat_minute,              # 13: 纬度分
            lat_second,              # 14: 纬度秒
            lat_direction,           # 15: 纬度方向
            lon_degree,              # 16: 经度度
            lon_minute,              # 17: 经度分
            lon_second,              # 18: 经度秒
            lon_direction,           # 19: 经度方向
            azimuth_h,               # 20: 方位角高八位
            azimuth_l,               # 21: 方位角低八位
            velocity,                # 22: 速度
            eyepoint_height,         # 23: 摄像机高度
            bat_voltage,             # 24: 电池电压
            soc                      # 25: 剩余电量
        ]
        
        # 最终安全检查：确保所有值都在 0-255 范围内
        data_bytes = [int(max(0, min(255, byte))) for byte in data_bytes]
        
        # ========== 4. 计算校验和（1-25字节和的低8位） ==========
        checksum = sum(data_bytes) & 0xFF
        
        # ========== 5. 构建完整数据包（0-27字节） ==========
        # 结构：包头 + 核心数据(25字节) + 校验和 + 包尾
        packet = bytes([RobotProtocol.SEND_HEAD] + data_bytes + [checksum, RobotProtocol.SEND_TAIL])
        
        return packet
    
    @staticmethod
    def unpack_robot_data(packet: bytes) -> Dict[str, Any]:
        """
        解包机器人数据
        
        参数:
            packet: 接收到的数据包
        
        返回:
            包含所有字段的字典
        
        异常:
            ValueError: 数据包格式错误
        """
        # ========== 1. 基础校验 ==========
        # 检查数据包长度
        if len(packet) != RobotProtocol.PACKET_SIZE:
            raise ValueError(f"数据包长度错误: {len(packet)} 字节 (期望 {RobotProtocol.PACKET_SIZE} 字节)")
        
        # 检查包头
        if packet[0] != RobotProtocol.SEND_HEAD:
            raise ValueError(f"包头错误: 0x{packet[0]:02X} (期望 0x{RobotProtocol.SEND_HEAD:02X})")
        
        # 检查包尾
        if packet[27] != RobotProtocol.SEND_TAIL:
            raise ValueError(f"包尾错误: 0x{packet[27]:02X} (期望 0x{RobotProtocol.SEND_TAIL:02X})")
        
        # ========== 2. 校验和验证 ==========
        # 核心数据段：1-25字节
        data_bytes = packet[1:26]
        received_checksum = packet[26]
        calculated_checksum = sum(data_bytes) & 0xFF
        
        if received_checksum != calculated_checksum:
            raise ValueError(
                f"校验和错误: 接收 0x{received_checksum:02X}, 计算 0x{calculated_checksum:02X}"
            )
        
        # ========== 3. 解析各个字段 ==========
        # 基础信息
        robot_id = packet[1]
        robot_status = packet[2]
        
        # 帧计数和果树编号（16位拼接）
        frame_index = (packet[3] << 8) | packet[4]
        left_tree_index = (packet[5] << 8) | packet[6]
        right_tree_index = (packet[7] << 8) | packet[8]
        
        # 时间
        hour = packet[9]
        minute = packet[10]
        second = packet[11]
        
        # GPS纬度
        lat_degree = packet[12]
        lat_minute = packet[13]
        lat_second = packet[14]
        lat_direction = packet[15]
        
        # GPS经度
        lon_degree = packet[16]
        lon_minute = packet[17]
        lon_second = packet[18]
        lon_direction = packet[19]
        
        # 行进方向（双字节拼接）
        azimuth = (packet[20] << 8) | packet[21]
        
        # 其他传感器数据
        velocity = packet[22]
        eyepoint_height = packet[23]
        bat_voltage = packet[24]
        soc = packet[25]
        
        # ========== 4. 格式转换和映射 ==========
        # GPS方向转字符
        lat_dir_char = chr(lat_direction) if lat_direction in [0x4E, 0x53] else '?'
        lon_dir_char = chr(lon_direction) if lon_direction in [0x45, 0x57] else '?'
        
        # 机器人ID映射
        robot_id_map = {1: 'robotA', 2: 'robotB', 3: 'robotC'}
        robot_name = robot_id_map.get(robot_id, f'robot{robot_id}')
        
        # 机器人状态映射（新增）
        robot_status_map = {
            0: 'moving',
            1: 'near_tree',
            2: 'charging',
            255: 'fault'
        }
        robot_status_name = robot_status_map.get(robot_status, 'unknown')
        
        # ========== 5. 构建返回字典 ==========
        return {
            'robot_id': robot_id,
            'robot_name': robot_name,
            'robot_status': robot_status,
            'robot_status_name': robot_status_name,
            'frame_index': frame_index,
            'tree_index': {
                'left': left_tree_index,
                'right': right_tree_index
            },
            'time': {
                'hour': hour,
                'minute': minute,
                'second': second,
                'formatted': f"{hour:02d}:{minute:02d}:{second:02d}"
            },
            'gps': {
                'latitude': {
                    'degree': lat_degree,
                    'minute': lat_minute,
                    'second': lat_second,
                    'direction': lat_dir_char,
                    'decimal': RobotProtocol._dms_to_decimal(lat_degree, lat_minute, lat_second, lat_dir_char)
                },
                'longitude': {
                    'degree': lon_degree,
                    'minute': lon_minute,
                    'second': lon_second,
                    'direction': lon_dir_char,
                    'decimal': RobotProtocol._dms_to_decimal(lon_degree, lon_minute, lon_second, lon_dir_char)
                }
            },
            'azimuth': azimuth,                           # 方位角（度）
            'velocity': velocity * 0.1,                   # 速度（m/s）
            'eyepoint_height': eyepoint_height * 0.01,    # 摄像机高度（m）
            'battery_voltage': bat_voltage * 0.1,         # 电池电压（V）
            'soc': soc,                                   # 剩余电量（%）
            'checksum': received_checksum
        }
    
    @staticmethod
    def _dms_to_decimal(degree: int, minute: int, second: int, direction: str) -> float:
        """
        将度分秒转换为十进制度数
        
        参数:
            degree: 度
            minute: 分
            second: 秒
            direction: 方向 ('N', 'S', 'E', 'W')
        
        返回:
            十进制度数
        """
        decimal = degree + minute / 60.0 + second / 3600.0
        if direction in ['S', 'W']:
            decimal = -decimal
        return decimal
    
    @staticmethod
    def decimal_to_dms(decimal: float, is_latitude: bool = True) -> Tuple[int, int, int, int]:
        """
        将十进制度数转换为度分秒
        
        参数:
            decimal: 十进制度数
            is_latitude: True表示纬度，False表示经度
        
        返回:
            (度, 分, 秒, 方向代码)
        """
        # 确定方向
        if is_latitude:
            direction = RobotProtocol.LAT_NORTH if decimal >= 0 else RobotProtocol.LAT_SOUTH
        else:
            direction = RobotProtocol.LON_EAST if decimal >= 0 else RobotProtocol.LON_WEST
        
        # 取绝对值
        decimal = abs(decimal)
        
        # 计算度分秒
        degree = int(decimal)
        minute_decimal = (decimal - degree) * 60
        minute = int(minute_decimal)
        second = int((minute_decimal - minute) * 60)
        
        # 确保数值在有效范围内（防止浮点数精度问题导致的60秒或60分）
        second = min(second, 59)
        minute = min(minute, 59)
        
        return degree, minute, second, direction


# ========== 测试示例 ==========
if __name__ == "__main__":
    # 打包示例
    pack_data = RobotProtocol.pack_robot_data(
        robot_id=1,
        robot_status=1,
        frame_index=1234,
        left_tree_index=567,
        right_tree_index=890,
        hour=10,
        minute=20,
        second=30,
        lat_degree=30,
        lat_minute=15,
        lat_second=20,
        lat_direction=RobotProtocol.LAT_NORTH,
        lon_degree=120,
        lon_minute=30,
        lon_second=40,
        lon_direction=RobotProtocol.LON_EAST,
        azimuth=90,
        velocity=50,
        eyepoint_height=150,
        bat_voltage=240,
        soc=80
    )
    print(f"打包后的数据包长度: {len(pack_data)} 字节")
    print(f"数据包十六进制: {pack_data.hex()}")
    
    # 解包示例
    try:
        unpack_data = RobotProtocol.unpack_robot_data(pack_data)
        print("\n解包结果:")
        print(f"机器人名称: {unpack_data['robot_name']}")
        print(f"运行状态: {unpack_data['robot_status_name']}")
        print(f"左侧果树编号: {unpack_data['tree_index']['left']}")
        print(f"右侧果树编号: {unpack_data['tree_index']['right']}")
        print(f"GPS纬度(十进制): {unpack_data['gps']['latitude']['decimal']:.6f}°")
        print(f"行进方向: {unpack_data['azimuth']}°")
        print(f"速度: {unpack_data['velocity']} m/s")
        print(f"剩余电量: {unpack_data['soc']}%")
    except ValueError as e:
        print(f"解包失败: {e}")
