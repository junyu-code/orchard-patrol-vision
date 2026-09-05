"""应用配置中心。

这里保存可以提交到代码仓库的运行参数。平台登录账号密码不要写进代码，
本地凭据请放在 `config/platform_accounts.local.json`，该文件已加入 .gitignore。
"""

import os
from copy import deepcopy

from transport.camera_capabilities import default_camera_source, secondary_camera_source


# 界面显示名称与历史命令行预设的映射。保留旧键，避免已有脚本失效。
ORCHARD_NAMES = (
    "恭城柑桔果园",
    "兴安葡萄园",
    "农科所橘子园",
)
ORCHARD_PRESET_KEYS = {
    "恭城柑桔果园": "client_a",
    "兴安葡萄园": "client_b",
    "农科所橘子园": "client_b",
}


# 每个园区的地址目录。列表项同时保存展示文字和运行时所需字段，界面无需解析地址字符串。
ORCHARD_ENDPOINTS = {
    "恭城柑桔果园": {
        "HTTP": (
            {
                "label": "柑桔平台 HTTP",
                "url": "https://api.jdpm.hhzzss.cn/agriculture/position/robotPost",
            },
        ),
        "UDP": (
            {"label": "旧平台 UDP（43.139.69.203:10088）", "host": "43.139.69.203", "port": 10088},
        ),
        "RTMP": (
            {
                "label": "自定义 RTMP（可编辑）",
                "url": os.getenv("CLIENT_A_RTMP_URL", ""),
            },
        ),
    },
    "兴安葡萄园": {
        "HTTP": (),
        "UDP": (
            {"label": "统一平台 UDP（1.14.205.24:4926）", "host": "1.14.205.24", "port": 4926},
        ),
        "RTMP": tuple(
            {"label": name, "url": url}
            for name, url in (
                ("左路视频", "rtmp://gl.xsjny.com/live/vineyard1_robot1_sensor1"),
                ("右路视频", "rtmp://gl.xsjny.com/live/vineyard1_robot1_sensor2"),
            )
        ),
    },
    "农科所橘子园": {
        "HTTP": (),
        "UDP": (
            {"label": "统一平台 UDP（1.14.205.24:4926）", "host": "1.14.205.24", "port": 4926},
        ),
        # 与葡萄园共用服务器，仅去掉 vineyard1_ 前缀。
        "RTMP": tuple(
            {"label": name, "url": url}
            for name, url in (
                ("左路视频", "rtmp://gl.xsjny.com/live/robot1_sensor1"),
                ("右路视频", "rtmp://gl.xsjny.com/live/robot1_sensor2"),
            )
        ),
    },
}


# 数据来源总开关：real | debug | simulation；默认调试模式
DATA_MODE = "debug"


# 平台入口备忘：地址目录已按园区维护；历史账号键仍在 platform_accounts.local.json 中兼容保留。
# 恭城柑桔果园平台：https://judaonongye.hhzzss.cn/index
# 兴安葡萄园/农科所橘子园统一平台：https://gl.xsjny.com/web/robot-analysis-ui/#/analytics

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
        # 当前进程推左路；右路可改用 RTMP_URL_RIGHT 或 --rtmp-url 覆盖。
        "RTMP_URL": "rtmp://gl.xsjny.com/live/vineyard1_robot1_sensor1",
        "RTMP_URL_LEFT": "rtmp://gl.xsjny.com/live/vineyard1_robot1_sensor1",
        "RTMP_URL_RIGHT": "rtmp://gl.xsjny.com/live/vineyard1_robot1_sensor2",
        "ROBOT_ID": 1,
        "SENSOR_ID": 1,
        "ENABLE_UDP": True,
        "UDP_HOST": "1.14.205.24",
        "UDP_PORT": 4926,
        "UDP_ORCHARD_ID": "vineyard1",
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
        "RTMP_RESOLUTION": "source",
        "RTMP_MAX_FPS": 0,
        "RTMP_VIDEO_BITRATE": "3000k",
        "RTMP_MAXRATE": "3600k",
        "RTMP_BUFSIZE": "6000k",
        "RAW_FRAME_TARGET_FPS": 0,
        "PLAYBACK_RATE_FPS": 0,
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
        "RTMP_RESOLUTION": "source",
        "RTMP_MAX_FPS": 0,
        "RTMP_VIDEO_BITRATE": "3000k",
        "RTMP_MAXRATE": "3600k",
        "RTMP_BUFSIZE": "6000k",
        "RAW_FRAME_TARGET_FPS": 0,
        "PLAYBACK_RATE_FPS": 0,
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
    "ORCHARD_NAME": "兴安葡萄园" if ACTIVE_PRESET == "client_b" else "恭城柑桔果园",
    "DATA_MODE": DATA_MODE,
    "DATA_PROTOCOL": "UDP" if ACTIVE_PRESET == "client_b" else "HTTP",
    "VIDEO_PROTOCOL": "RTMP",

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

    # 双路 EM22 HID POS 标签扫描器；默认开启，序列号用于固定左右，不依赖 USB 枚举顺序
    "ENABLE_HID_TAG_SCANNERS": True,
    "HID_TAG_VENDOR_ID": 0x1EAB,
    "HID_TAG_PRODUCT_ID": 0x0010,
    "HID_TAG_LEFT_SERIAL": os.getenv("HID_TAG_LEFT_SERIAL", "AB031246"),
    "HID_TAG_RIGHT_SERIAL": os.getenv("HID_TAG_RIGHT_SERIAL", "AB030000"),
    "USE_HID_TAG_TREE_IDS": True,
    # 二维码果树编号在 30 分钟内有效；超时后按无树处理
    "HID_TAG_STALE_TIMEOUT": 30 * 60.0,
    "HID_TAG_DUPLICATE_INTERVAL": 0.3,
    "HID_TAG_RECONNECT_INTERVAL": 2.0,
    "HID_TAG_POLL_INTERVAL": 0.01,
    "HID_TAG_ENCODING": "utf-8",
    "HID_TAG_PATTERN": r"^(?:TREE[:_-]?)?(?P<tree_id>\d{1,5})$",

    # YOLO 模型配置
    "WEIGHTS": "./pt/best.pt",
    "SOURCE": default_camera_source(),
    # 双路相机固定绑定；Linux 优先使用 /dev/v4l/by-path/*-video-index0 稳定路径
    "CAMERA_SOURCE_LEFT": os.getenv("CAMERA_LEFT_SOURCE", default_camera_source()),
    "CAMERA_SOURCE_RIGHT": os.getenv("CAMERA_RIGHT_SOURCE", secondary_camera_source()),
    "CONF_THRES": 0.8,
    "IOU_THRES": 0.45,
    "IMG_SIZE": 640,
    "RAW_STREAM_ONLY": False,
    "LOOP_SOURCE": True,
    "CAMERA_RECONNECT_INTERVAL": 1.0,

    # RTMP 推流配置
    "RTMP_MAX_WIDTH": 1280,
    "RTMP_RESOLUTION": "source",
    "RTMP_MAX_FPS": 0,
    "RTMP_FRAME_RATE": "source",
    "RTMP_VIDEO_BITRATE": "3000k",
    "RTMP_MAXRATE": "3600k",
    "RTMP_BUFSIZE": "6000k",
    "RAW_FRAME_TARGET_FPS": 0,
    "PLAYBACK_RATE_FPS": 0,
    "RTMP_TIMESTAMP_OVERLAY": False,
    "RTMP_TIME_STANDARD": "local",
    "RTMP_RECONNECT_INTERVAL": 3.0,

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
    requested_name = preset_name or ACTIVE_PRESET
    # 新界面使用园区中文名称；历史 client_* 键继续支持命令行和旧脚本。
    active_preset = ORCHARD_PRESET_KEYS.get(requested_name, requested_name)
    config = deepcopy(BASE_CONFIG)
    config.update(PRESET_CONFIGS.get(active_preset, PRESET_CONFIGS["client_a"]))
    config["PRESET_NAME"] = active_preset
    # 主检测线程使用固定绑定的左路设备。
    config["SOURCE"] = config.get("CAMERA_SOURCE_LEFT", default_camera_source())
    config["DATA_PROTOCOL"] = "HTTP" if config.get("ENABLE_HTTP") else "UDP"
    config["VIDEO_PROTOCOL"] = "RTMP" if config.get("ENABLE_RTMP") else "NONE"
    if requested_name in ORCHARD_NAMES:
        config["ORCHARD_NAME"] = requested_name
        endpoint_config = ORCHARD_ENDPOINTS[requested_name]
        data_protocol = config["DATA_PROTOCOL"]
        data_endpoint = endpoint_config.get(data_protocol, ())
        if data_endpoint:
            selected_data = data_endpoint[0]
            if data_protocol == "HTTP":
                config["HTTP_URL"] = selected_data.get("url", "")
            elif data_protocol == "UDP":
                config["UDP_HOST"] = selected_data.get("host", "")
                config["UDP_PORT"] = int(selected_data.get("port", 0) or 0)
        video_endpoint = endpoint_config.get("RTMP", ())
        if video_endpoint:
            config["RTMP_URL"] = video_endpoint[0].get("url", "")
        if not config.get("RTMP_URL"):
            # 恭城果园的图片随 HTTP JSON 上传，没有独立 RTMP 视频流。
            config["ENABLE_RTMP"] = False
            config["VIDEO_PROTOCOL"] = "NONE"
    elif active_preset == "client_b":
        config["ORCHARD_NAME"] = "兴安葡萄园"
    else:
        config["ORCHARD_NAME"] = "恭城柑桔果园"
    return config
