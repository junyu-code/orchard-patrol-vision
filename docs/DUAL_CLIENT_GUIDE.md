# 双甲方对接使用指南

本项目已完成双甲方系统对接优化，支持灵活切换或同时对接两套系统。

## 📋 配置方案

### 甲方 A（原系统）
- **管理平台**: https://judaonongye.hhzzss.cn/index
- **HTTP 上报**: https://api.jdpm.hhzzss.cn/agriculture/position/robotPost
- **RTMP 推流**: rtmp://sip.jdny.hhzzss.cn:21935/xiaoche/xiaoche002
- **协议**: HTTP POST + RTMP

### 甲方 B（新统一平台）
- **UDP 数据**: 1.14.205.24:4926
- **左路 RTMP**: rtmp://gl.xsjny.com/live/robot1_sensor1
- **右路 RTMP**: rtmp://gl.xsjny.com/live/robot1_sensor2
- **管理平台**: https://gl.xsjny.com/web/robot-analysis-ui/#/analytics
- **大屏**: https://gl.xsjny.com/web/robot-data-view/index.html
- **协议**: UDP 二进制协议 + RTMP

平台登录凭据保存在本地忽略文件 `config/platform_accounts.local.json`，提交到 GitHub 时只保留 `config/platform_accounts.example.json`。

主程序一个进程对应一个视频源和一路 RTMP。`client_b` 当前默认右路 `sensor2`；
推左路时将 `RTMP_URL` 改为 `RTMP_URL_LEFT`，并把 `SENSOR_ID` 改为 `1`。
左右相机同时在线需要分别启动采集进程，UDP 遥测只应由其中一个进程上报，避免重复数据。

## 🔧 快速切换配置

在 `config/app_config.py` 中修改 `ACTIVE_PRESET` 变量：

```python
# 🔧 在这里选择使用哪个配置：'client_a' | 'client_b' | 'both'
ACTIVE_PRESET = "client_a"  # 默认使用甲方A的配置
```

### 选项说明

| 配置值 | 说明 | HTTP | UDP | RTMP |
|--------|------|------|-----|------|
| `"client_a"` | 仅对接甲方A | ✅ | ❌ | ✅ (甲方A地址) |
| `"client_b"` | 仅对接甲方B | ❌ | ✅ | ✅ (甲方B地址) |
| `"both"` | 同时对接两家 | ✅ | ✅ | ✅ (甲方B地址) |

## 📦 配置详情

### 预设配置定义（config/app_config.py）

```python
import os

PRESET_CONFIGS = {
    "client_a": {
        "ENABLE_HTTP": True,
        "HTTP_URL": "https://api.jdpm.hhzzss.cn/agriculture/position/robotPost",
        "ENABLE_RTMP": True,
        "RTMP_URL": os.getenv("CLIENT_A_RTMP_URL", ""),
        "ENABLE_UDP": False,
    },
    "client_b": {
        "ENABLE_HTTP": False,
        "ENABLE_RTMP": True,
        "RTMP_URL": "rtmp://gl.xsjny.com/live/robot1_sensor2",
        "RTMP_URL_LEFT": "rtmp://gl.xsjny.com/live/robot1_sensor1",
        "RTMP_URL_RIGHT": "rtmp://gl.xsjny.com/live/robot1_sensor2",
        "ENABLE_UDP": True,
        "UDP_HOST": "1.14.205.24",
        "UDP_PORT": 4926,
        "RTMP_TIMESTAMP_OVERLAY": True,
        "RTMP_TIME_STANDARD": "utc+8",
        "UDP_TIME_STANDARD": "utc+8",
    },
    "both": {
        # 所有功能都启用
    }
}
```

甲方 A 的真实 RTMP 地址可能包含签名，应通过 `CLIENT_A_RTMP_URL` 环境变量在部署机器本地配置，不得提交到仓库或写入文档。

## 🚀 使用流程

### 1. 对接甲方A（默认）

```bash
# config/app_config.py 中设置
ACTIVE_PRESET = "client_a"

# 运行程序
python main.py
```

程序启动后会显示：
```
🚀 检测线程启动
   配置方案: client_a
   HTTP: ✅ | RTMP: ✅ | UDP: ❌
```

### 2. 切换到甲方B

```python
# config/app_config.py 中修改为
ACTIVE_PRESET = "client_b"
```

运行后显示：
```
🚀 检测线程启动
   配置方案: client_b
   HTTP: ❌ | RTMP: ✅ | UDP: ✅
```

### 3. 同时对接两家（测试用）

```python
ACTIVE_PRESET = "both"
```

## 📡 数据传输说明

### HTTP 上报（甲方A）
- **频率**: 检测到病害时立即上报，间隔 2 秒
- **数据**: GPS、病害类型、置信度、图片（Base64）
- **日志**: `📤 HTTP 上报 | 帧:123 | 病害:5`

### UDP 上报（甲方B）
- **频率**: 每秒一次（无论是否检测到病害）
- **协议**: 28 字节二进制协议
- **数据**: 机器人ID、状态、GPS、果树编号、电池电压等
- **时间**: 原有三字节时间字段发送北京时间（`UTC+8`）`HH:MM:SS`，包长不变
- **日志**: `📡 UDP 上报 | 帧:123 | 病害检测`

### RTMP 推流
- **分辨率**: 默认继承相机/视频源分辨率；选择固定档位时保持原比例
- **帧率**: 默认继承源帧率；选择较低档位时丢弃中间帧并按目标帧率节流
- **码率**: 默认 3000k，峰值 3600k
- **编码**: H.264
- **时间**: 远端视频左上角叠加 ISO-8601 北京时间及 `+08:00` 偏移

18 Mbps 环境可按需运行两路 `720p / 30fps / 3000k`。两路编码峰值合计约
7.2 Mbps；确认大屏并发拉流和服务器出口稳定后，再用 `tools/rtmp_probe.py`
单路测试 `1080p_25fps_4500k`。大屏每增加一个无转码观看端，服务器出口通常还会
增加相应视频码率，因此不把 1080p 直接设为默认。

UDP 协议没有日期、毫秒和时区字段；如需平台保存绝对时间戳，应由甲方同步升级
收发协议。当前方案依靠服务器/视觉主机 NTP 校时，用视频完整的 `UTC+8` 水印与
UDP 北京时间 `HH:MM:SS` 对齐。

## 🔍 验证对接

### 甲方A验证
- 查看控制台日志 `📤 HTTP 上报`
- 检查甲方A平台是否收到数据

### 甲方B验证
1. **UDP数据**: 查看日志 `📡 UDP 上报`
2. **RTMP推流**: 访问管理平台
   - URL: https://gl.xsjny.com/web/robot-analysis-ui/#/analytics
   - 账号密码见本地 `config/platform_accounts.local.json`
   - 查看左路 `robot1_sensor1` 或右路 `robot1_sensor2` 视频流

## ⚙️ 高级配置

### 修改机器人ID（用于甲方B）

```python
CONFIG = {
    # ...
    "ROBOT_ID": 1,    # 1=robot1, 2=robot2, 3=robot3
    "SENSOR_ID": 1,   # 1=sensor1, 2=sensor2
}
```

对应的推流地址会是：
- robot1_sensor1
- robot2_sensor1
- robot3_sensor2

### 调整发送频率

```python
# DetThread.__init__ 方法中
self.http_send_interval = 2.0  # HTTP 发送间隔（秒）
self.udp_send_interval = 1.0   # UDP 发送间隔（秒）
```

## 📂 项目结构

```
transport/
├── http_sender.py      # HTTP 上报模块（甲方A）
├── udp_sender.py       # UDP 上报模块（甲方B）[新增]
├── rtmp_sender.py      # RTMP 推流模块
├── robot_protocol.py   # UDP 协议定义[新增]
└── virtual_sensor.py   # 虚拟传感器模拟

samples/videos/robot_push/
├── test0_push.mp4           # 甲方B主要测试视频
├── test0_pingpong.mp4       # 正序+逆序循环演示视频
└── test_demo.mp4            # 外部演示视频

tools/
├── robot_udp_simulator.py   # UDP 独立测试工具
├── test-video-push.bat      # RTMP/RTSP 独立推流测试
└── video_reverse_merge.py   # 正序+逆序视频生成工具

scripts/
└── run-client-b-demo.bat     # 甲方B演示入口，调用 main.py
```

## 🐛 故障排查

### UDP 发送失败
```bash
❌ UDP 发送失败: [Errno 10061] Connection refused
```
- 检查防火墙是否开放 UDP 端口
- 确认服务器地址和端口正确
- 使用 `tools/robot_udp_simulator.py` 测试连接

### RTMP 推流卡顿
- 检查网络带宽
- 甲方B默认跟随相机原生分辨率和帧率，码率约 `3000k`；上行带宽不足时可在界面选择较低分辨率/帧率
- 检查目标服务器负载

### HTTP 上报失败
```bash
❌ HTTP 发送失败: HTTPError
```
- 检查 HTTP_URL 是否正确
- 确认网络连接
- 查看甲方服务器日志

## 📝 更新日志

### 2024-06-24
- ✅ 添加 UDP 数据上报支持（甲方B）
- ✅ 集成果园机器人 UDP 协议
- ✅ 实现双甲方配置预设系统
- ✅ 支持配置一键切换
- ✅ 优化启动日志显示当前配置
- ✅ 添加 UDP 资源自动清理

## 💡 建议

1. **开发测试**: 使用 `"client_a"` 或 `"client_b"` 单独测试
2. **联调验证**: 短期使用 `"both"` 同时验证两套系统
3. **生产环境**: 根据实际需求选择对应的配置方案
4. **性能考虑**: 同时对接可能增加系统负载，建议根据硬件配置选择

## 📞 技术支持

如有问题，请检查：
1. 控制台日志输出
2. 配置方案选择是否正确
3. 网络连接状态
4. 甲方平台状态
