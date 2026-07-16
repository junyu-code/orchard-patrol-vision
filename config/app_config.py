"""应用配置中心。

这里保存可以提交到代码仓库的运行参数。平台登录账号密码不要写进代码，
本地凭据请放在 `config/platform_accounts.local.json`，该文件已加入 .gitignore。
"""

import os
from copy import deepcopy


# 数据来源总开关：real | debug | simulation；默认调试模式
DATA_MODE = "debug"


# 平台入口备忘：
# 甲方A平台：https://judaonongye.hhzzss.cn/index
# 甲方A本地凭据：CLIENT_A_USERNAME / CLIENT_A_PASSWORD 或 config/platform_accounts.local.json
# 甲方B管理平台：https://gl.xsjny.com/web/robot-analysis-ui/#/analytics
# 甲方B大屏：https://gl.xsjny.com/web/robot-data-view/index.html
# 甲方B本地凭据：CLIENT_B_USERNAME / CLIENT_B_PASSWORD 或 config/platform_accounts.local.json

# 预设配置方案：方便在不同甲方之间切换
PRESET_CONFIGS = {
    # 甲方A：原有的 HTTP + RTMP 系统
    "client_a": {
        "ENABLE_HTTP": True,
        "HTTP_URL": "https://api.jdpm.hhzzss.cn/agriculture/position/robotPost",
        "ENABLE_RTMP": True,
        "RTMP_URL": os.getenv("CLIENT_A_RTMP_URL", ""),
        "ENABLE_UDP": False,
        "UDP_HOST": "",
        "UDP_PORT": 0,
        "RAW_STREAM_ONLY": False,
        "SIMULATE_TREE_EVENTS": False,
        "ENABLE_PATROL_TIMELINE": False,
    },

    # 甲方B：新的统一平台，使用 UDP + RTMP
    "client_b": {
        "ENABLE_HTTP": False,
        "HTTP_URL": "",
        "ENABLE_RTMP": True,
        # 当前进程推右路；左路可改用 RTMP_URL_LEFT 或 --rtmp-url 覆盖。
        "RTMP_URL": "rtmp://gl.xsjny.com/live/robot1_sensor2",
        "RTMP_URL_LEFT": "rtmp://gl.xsjny.com/live/robot1_sensor1",
        "RTMP_URL_RIGHT": "rtmp://gl.xsjny.com/live/robot1_sensor2",
        "SENSOR_ID": 2,
        "ENABLE_UDP": True,
        "UDP_HOST": "1.14.205.24",
        "UDP_PORT": 4926,
        "UDP_ORCHARD_ID": "orchard1",
        "UDP_ADD_ORCHARD_PREFIX": True,
        "RAW_STREAM_ONLY": True,
        "SIMULATE_TREE_EVENTS": False,
        "ENABLE_PATROL_TIMELINE": True,
        "PATROL_SOURCE_NAME": "test0_push.mp4",
        "PATROL_TREE_TIMES": [1, 5, 9, 13, 17, 22, 27, 31, 35, 39],
        "PATROL_START_TREE_ID": 1,
        "PATROL_TIMELINE_DEBUG": False,
        "UDP_TREE_EVENT_DEBUG": False,
        "PINGPONG_SOURCE": True,
        "RTMP_MAX_WIDTH": 1280,
        "RTMP_RESOLUTION": "1280x720",
        "RTMP_MAX_FPS": 30,
        "RTMP_VIDEO_BITRATE": "3000k",
        "RTMP_MAXRATE": "3600k",
        "RTMP_BUFSIZE": "6000k",
        "RAW_FRAME_TARGET_FPS": 30,
        "PLAYBACK_RATE_FPS": 30,
        "RTMP_TIMESTAMP_OVERLAY": True,
        "RTMP_TIME_STANDARD": "utc+8",
        "UDP_TIME_STANDARD": "utc+8",
        "UDP_VERBOSE_LOG": True,
        "UDP_LOG_INTERVAL": 5,
        "USE_SYSTEM_LOCATION": False,
        "SIM_BASE_LAT": 25.28,
        "SIM_BASE_LON": 110.34,
    },

    # 同时对接两家，主要用于联调测试
    "both": {
        "ENABLE_HTTP": True,
        "HTTP_URL": "https://api.jdpm.hhzzss.cn/agriculture/position/robotPost",
        "ENABLE_RTMP": True,
        "RTMP_URL": "rtmp://gl.xsjny.com/live/robot1_sensor1",
        "RTMP_URL_LEFT": "rtmp://gl.xsjny.com/live/robot1_sensor1",
        "RTMP_URL_RIGHT": "rtmp://gl.xsjny.com/live/robot1_sensor2",
        "ENABLE_UDP": True,
        "UDP_HOST": "1.14.205.24",
        "UDP_PORT": 4926,
        "UDP_ORCHARD_ID": "orchard1",
        "UDP_ADD_ORCHARD_PREFIX": True,
        "RAW_STREAM_ONLY": True,
        "SIMULATE_TREE_EVENTS": False,
        "ENABLE_PATROL_TIMELINE": True,
        "PATROL_SOURCE_NAME": "test0_push.mp4",
        "PATROL_TREE_TIMES": [1, 5, 9, 13, 17, 22, 27, 31, 35, 39],
        "PATROL_START_TREE_ID": 1,
        "PATROL_TIMELINE_DEBUG": False,
        "UDP_TREE_EVENT_DEBUG": False,
        "PINGPONG_SOURCE": True,
        "RTMP_MAX_WIDTH": 1280,
        "RTMP_RESOLUTION": "1280x720",
        "RTMP_MAX_FPS": 30,
        "RTMP_VIDEO_BITRATE": "3000k",
        "RTMP_MAXRATE": "3600k",
        "RTMP_BUFSIZE": "6000k",
        "RAW_FRAME_TARGET_FPS": 30,
        "PLAYBACK_RATE_FPS": 30,
        "RTMP_TIMESTAMP_OVERLAY": True,
        "RTMP_TIME_STANDARD": "utc+8",
        "UDP_TIME_STANDARD": "utc+8",
        "UDP_VERBOSE_LOG": True,
        "UDP_LOG_INTERVAL": 5,
        "USE_SYSTEM_LOCATION": False,
        "SIM_BASE_LAT": 25.28,
        "SIM_BASE_LON": 110.34,
    },
}

# 在这里选择默认配置：'client_a' | 'client_b' | 'both'
ACTIVE_PRESET = "client_b"
PRESET_NAMES = tuple(PRESET_CONFIGS.keys())

BASE_CONFIG = {
    "PRESET_NAME": ACTIVE_PRESET,
    "DATA_MODE": DATA_MODE,

    # 旧病害发送串口；当前主流程不向电控返回数据
    "ENABLE_SERIAL": False,
    "SERIAL_PORT": "COM13",
    "BAUDRATE": 9600,

    # 电控统一遥测串口（58 字节 OP-Telemetry V1）
    "ENABLE_TELEMETRY_SERIAL": False,
    "TELEMETRY_SERIAL_PORT": os.getenv("TELEMETRY_SERIAL_PORT", ""),
    "TELEMETRY_SERIAL_BAUDRATE": 9600,
    "TELEMETRY_SERIAL_READ_TIMEOUT": 0.2,
    "TELEMETRY_STALE_TIMEOUT": 1.0,
    "TELEMETRY_RECONNECT_INTERVAL": 2.0,
    "TELEMETRY_MAX_BUFFER_BYTES": 4096,
    "TELEMETRY_SERIAL_AUTO_DETECT": True,
    "TELEMETRY_SERIAL_PROBE_TIMEOUT": 1.5,

    # GPS 串口接收配置，与病害串口发送器相互独立
    "ENABLE_GPS_SERIAL": False,
    "GPS_SERIAL_PORT": "",
    "GPS_SERIAL_BAUDRATE": 9600,
    "GPS_SERIAL_READ_TIMEOUT": 0.2,
    "GPS_STALE_TIMEOUT": 1.0,
    "GPS_RECONNECT_INTERVAL": 2.0,
    "GPS_MAX_BUFFER_BYTES": 4096,
    "GPS_SERIAL_AUTO_DETECT": True,
    "GPS_SERIAL_PROBE_TIMEOUT": 1.5,
    "GPS_SPEED_MIN_INTERVAL": 1.0,
    "GPS_SPEED_MAX_INTERVAL": 5.0,
    "GPS_SPEED_MIN_DISTANCE": 0.3,
    "GPS_SPEED_MAX_MPS": 8.0,
    "GPS_SPEED_SMOOTHING_ALPHA": 0.35,
    "GPS_EVENT_LOG_DIR": "./result/gps_events",
    "GPS_EVENT_LOG_RETENTION_DAYS": 3,

    # YOLO 模型配置
    "WEIGHTS": "./pt/best.pt",
    "SOURCE": "0",
    "CONF_THRES": 0.8,
    "IOU_THRES": 0.45,
    "IMG_SIZE": 640,
    "RAW_STREAM_ONLY": False,
    "LOOP_SOURCE": True,

    # RTMP 推流配置
    "RTMP_MAX_WIDTH": 1280,
    "RTMP_RESOLUTION": "1280x720",
    "RTMP_MAX_FPS": 30,
    "RTMP_VIDEO_BITRATE": "3000k",
    "RTMP_MAXRATE": "3600k",
    "RTMP_BUFSIZE": "6000k",
    "RAW_FRAME_TARGET_FPS": 0,
    "PLAYBACK_RATE_FPS": 0,
    "RTMP_TIMESTAMP_OVERLAY": False,
    "RTMP_TIME_STANDARD": "local",

    # 机器人标识，用于甲方B UDP 协议
    "ROBOT_ID": 1,
    "SENSOR_ID": 1,
    "UDP_ORCHARD_ID": "orchard1",
    "UDP_ADD_ORCHARD_PREFIX": False,
    "SIMULATE_TREE_EVENTS": False,
    "TREE_INTERVAL": 8,
    "TREE_JITTER": 2,
    "TREE_HOLD_FRAMES": 5,
    "UDP_VERBOSE_LOG": False,
    "UDP_LOG_INTERVAL": 5,
    "UDP_TIME_STANDARD": "local",
    "USE_SYSTEM_LOCATION": False,
    "SIM_BASE_LAT": 25.28,
    "SIM_BASE_LON": 110.34,
    "ENABLE_PATROL_TIMELINE": False,
    "PATROL_SOURCE_NAME": "test0_push.mp4",
    "PATROL_TREE_TIMES": [],
    "PATROL_START_TREE_ID": 1,
    "PATROL_TIMELINE_DEBUG": False,
    "UDP_TREE_EVENT_DEBUG": False,
    "PINGPONG_SOURCE": False,
}


def build_config(preset_name=None):
    """构建运行配置，避免外部直接修改全局模板。"""
    active_preset = preset_name or ACTIVE_PRESET
    config = deepcopy(BASE_CONFIG)
    config.update(PRESET_CONFIGS.get(active_preset, PRESET_CONFIGS["client_a"]))
    config["PRESET_NAME"] = active_preset
    return config
