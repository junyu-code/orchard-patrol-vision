"""项目运行默认值。

修改园区地址时只需要编辑本文件；运行时配置会从这里读取。
部署机器上的环境变量可以临时覆盖需要保密或临时变更的地址。
"""

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
NONGKESUO_RTMP_LEFT = "rtmp://gl.xsjny.com/live/robot1_sensor1"
NONGKESUO_RTMP_RIGHT = "rtmp://gl.xsjny.com/live/robot1_sensor2"

# 同时联调两套平台时使用的流名
BOTH_RTMP_LEFT = "rtmp://gl.xsjny.com/live/robot1_sensor1"
BOTH_RTMP_RIGHT = "rtmp://gl.xsjny.com/live/robot1_sensor2"
