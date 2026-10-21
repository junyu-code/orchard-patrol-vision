"""项目运行默认值。

修改园区地址时只需要编辑本文件；运行时配置会从这里读取。
部署机器上的环境变量可以临时覆盖需要保密或临时变更的地址。
"""

# 通用运行默认值：切换默认果园或调整默认推流参数时修改这里。
DEFAULT_PRESET = "client_a"
DEFAULT_ORCHARD_NAME = "恭城柑桔果园"
DEFAULT_RTMP_MAX_WIDTH = 1280
DEFAULT_RTMP_RESOLUTION = "source"
DEFAULT_RTMP_MAX_FPS = 0
DEFAULT_RTMP_FRAME_RATE = "source"
DEFAULT_RTMP_VIDEO_BITRATE = "3000k"
DEFAULT_RTMP_MAXRATE = "3600k"
DEFAULT_RTMP_BUFSIZE = "6000k"
DEFAULT_RAW_FRAME_TARGET_FPS = 0
DEFAULT_PLAYBACK_RATE_FPS = 0

# 恭城柑桔果园
GONGCHENG_HTTP_URL = "https://api.jdpm.hhzzss.cn/agriculture/position/robotPost"
GONGCHENG_RTMP_URL = (
    "rtmp://zlmediakit.aly01.hhzzss.cn:19350/116/D13Z94P4P30H"
    "?sign=41db35390ddad33f83944f44b8b75ded"
)
GONGCHENG_UDP_HOST = "43.139.69.203"
GONGCHENG_UDP_PORT = 10088

# 兴安葡萄园
XINGAN_UDP_HOST = "1.14.205.24"
XINGAN_UDP_PORT = 4926
XINGAN_ORCHARD_ID = "vineyard1"
XINGAN_RTMP_LEFT = "rtmp://gl.xsjny.com/live/vineyard1_robot1_sensor1"
XINGAN_RTMP_RIGHT = "rtmp://gl.xsjny.com/live/vineyard1_robot1_sensor2"

# 农科所橘子园
NONGKESUO_UDP_HOST = "1.14.205.24"
NONGKESUO_UDP_PORT = 4926
NONGKESUO_ORCHARD_ID = "orchard3"
NONGKESUO_RTMP_LEFT = "rtmp://gl.xsjny.com/live/py_orchard1_robot1_sensor1"
NONGKESUO_RTMP_RIGHT = "rtmp://gl.xsjny.com/live/py_orchard1_robot1_sensor2"
