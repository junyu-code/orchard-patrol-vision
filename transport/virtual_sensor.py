import random
import math
import json
import urllib.request
import time

class VirtualSensorSimulator:
    """
    虚拟传感器模拟器
    模仿真实机器人的 GPS、电量、运动状态变化
    用于在缺乏真实硬件时测试 HTTP 上报功能
    """
    
    def __init__(self, lat_decimal=None, lon_decimal=None, use_system_location=False):
        # 1. 初始位置：优先使用传入位置；允许调试时尝试系统粗定位；失败则使用北京附近果园默认点
        base_lat, base_lon = 39.9042, 116.4074
        if use_system_location:
            located = self._load_system_location()
            if located:
                base_lat, base_lon = located
        has_config_location = lat_decimal is not None and lon_decimal is not None
        if has_config_location:
            base_lat, base_lon = float(lat_decimal), float(lon_decimal)

        # 配置明确传入经纬度时使用精确起点；无配置时才给默认点加随机偏移。
        gps_offset = 0.0 if has_config_location else 0.0003
        self.lat_decimal = base_lat + random.uniform(-gps_offset, gps_offset)
        self.lon_decimal = base_lon + random.uniform(-gps_offset, gps_offset)
        
        # 2. 运动状态
        self.azimuth = random.randint(0, 359)  # 0-359度
        self.velocity = random.uniform(0.8, 1.2)  # m/s
        self.is_moving = True
        
        # 3. 电源状态
        self.bat_voltage = 24.0                # V
        self.soc = 100.0                       # %
        self.last_update_time = time.time()
        
        # 4. 路径规划模拟
        self.route_index = 1
        self.waypoint_index = 0

    def update(self, frame_count, is_near_tree=False):
        """
        每帧调用一次，更新内部状态
        
        Args:
            frame_count (int): 当前帧数，用于计算路径点
            is_near_tree (bool): 是否检测到果树（检测到则停止移动）
        """
        now = time.time()
        elapsed = max(0.05, min(2.0, now - self.last_update_time))
        self.last_update_time = now

        # --- 1. 模拟 GPS 移动 ---
        if self.is_moving:
            # 小车持续行驶，速度在合理范围内轻微波动
            self.velocity += random.uniform(-0.08, 0.08)
            self.velocity = max(0.6, min(1.5, self.velocity))

            # 沿当前方位角移动
            rad = math.radians(self.azimuth)
            # 按真实经过时间估算位移，避免视频帧率变化导致路线漂移过快
            meters_per_degree = 111320.0
            distance = self.velocity * elapsed
            lat_delta = math.cos(rad) * distance / meters_per_degree
            lon_scale = max(0.2, math.cos(math.radians(self.lat_decimal)))
            lon_delta = math.sin(rad) * distance / (meters_per_degree * lon_scale)
            self.lat_decimal += lat_delta + random.uniform(-0.000002, 0.000002)
            self.lon_decimal += lon_delta + random.uniform(-0.000002, 0.000002)
            
            # 方位角轻微随机扰动，模拟真实巡检路线不是绝对直线
            self.azimuth = (self.azimuth + random.randint(-4, 4)) % 360
        else:
            # 静止时 GPS 会有微小漂移
            self.lat_decimal += random.uniform(-0.000001, 0.000001)
            self.lon_decimal += random.uniform(-0.000001, 0.000001)

        # --- 2. 模拟电量消耗 ---
        if self.soc > 0:
            # 移动时耗电快，静止时耗电慢
            consume_rate = (0.006 if self.is_moving else 0.002) * elapsed
            self.soc -= consume_rate
            self.soc = max(0, self.soc) # 不低于0
            
            # 电压随电量线性下降 (24V 满电 -> 20V 亏电)
            self.bat_voltage = 20.0 + (self.soc / 100.0) * 4.0

        # --- 3. 模拟路径点变化 ---
        # 每 100 帧切换一个 waypoint
        self.waypoint_index = (frame_count // 100) % 10

    def _load_system_location(self):
        """尝试使用系统网络粗定位；失败时返回 None。"""
        try:
            with urllib.request.urlopen("https://ipapi.co/json/", timeout=2) as response:
                data = json.loads(response.read().decode("utf-8", errors="ignore"))
            lat = data.get("latitude")
            lon = data.get("longitude")
            if lat is not None and lon is not None:
                return float(lat), float(lon)
        except Exception:
            return None
        return None

    def get_gps_dms(self):
        """
        将内部的十进制经纬度转换为度分秒 (DMS) 格式
        
        Returns:
            tuple: (lat_d, lat_m, lat_s, lat_dir, lon_d, lon_m, lon_s, lon_dir)
        """
        def decimal_to_dms(decimal_deg):
            d = int(decimal_deg)
            m_float = (abs(decimal_deg) - abs(d)) * 60
            m = int(m_float)
            s = (m_float - m) * 60
            return d, m, round(s, 2) # 秒保留两位小数

        lat_d, lat_m, lat_s = decimal_to_dms(self.lat_decimal)
        lon_d, lon_m, lon_s = decimal_to_dms(self.lon_decimal)
        
        lat_dir = "N" if self.lat_decimal >= 0 else "S"
        lon_dir = "E" if self.lon_decimal >= 0 else "W"
        
        return lat_d, lat_m, lat_s, lat_dir, lon_d, lon_m, lon_s, lon_dir

    def get_status_data(self):
        """
        获取当前的运动和电源状态
        
        Returns:
            dict: 包含速度、方位角、电压、电量、路径信息
        """
        return {
            "velocity": self.velocity if (self.is_moving) else 0.0,
            "azimuth": float(self.azimuth),
            "bat_voltage": round(self.bat_voltage, 1),
            "soc": int(self.soc),
            "route_index": self.route_index,
            "waypoint_index": self.waypoint_index,
            "eyepoint_height": round(random.uniform(1.45, 1.60), 2)
        }
