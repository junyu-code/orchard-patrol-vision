# orchard-patrol-vision

果园巡检视觉与推流系统，用于果园巡检小车的视频采集、病虫害识别、平台数据上报和 RTMP 视频推流。

项目当前保留 YOLOv5 检测能力，并在此基础上集成了两套甲方平台对接逻辑：

- 甲方 A：HTTP 病虫害数据上报 + RTMP 推流
- 甲方 B：UDP 机器人巡检遥测 + RTMP 推流

## 核心能力

- 本地视频、摄像头、RTSP 视频源接入
- YOLOv5 病虫害识别与检测结果展示
- RTMP 实时视频推流
- 甲方 A HTTP 数据上报
- 甲方 B UDP 二进制协议上报
- 甲方 B 本地演示视频正放/倒放循环推流
- 果树 ID、GPS、速度、方向、电池等巡检数据模拟
- 双甲方预设配置快速切换

## 目录结构

```text
orchard-patrol-vision/
├─ main.py                         # 主程序入口：界面、检测线程、上报和推流调度
├─ config/
│  ├─ app_config.py                # 双甲方运行配置
│  ├─ endpoints.json               # 当前和旧版平台地址备份
│  └─ platform_accounts.example.json
├─ transport/
│  ├─ http_sender.py               # 甲方 A HTTP 上报
│  ├─ udp_sender.py                # 甲方 B UDP 发送
│  ├─ robot_protocol.py            # 甲方 B UDP 数据包协议
│  ├─ patrol_timeline.py           # 甲方 B 巡检果树时间轴
│  ├─ virtual_sensor.py            # GPS、速度、方向、电池等虚拟传感器
│  └─ rtmp_sender.py               # RTMP 推流
├─ scripts/
│  └─ run-client-b-demo.bat         # 甲方 B 本地演示入口
├─ samples/
│  └─ videos/robot_push/            # 甲方 B 演示/测试视频
├─ tools/                           # 调试、诊断、辅助脚本
├─ docs/                            # 对接说明、流程图、结构说明
├─ pt/                              # 模型权重目录
├─ main_win/                        # 主界面 UI 文件
└─ dialog/                          # RTSP 输入弹窗
```

更多结构说明见 `docs/PROJECT_STRUCTURE.md`。

## 快速运行

### 1. 安装依赖

```bash
conda create -n yolov5_pyqt5 python=3.8
conda activate yolov5_pyqt5
pip install -r requirements.txt
```

模型权重放在 `pt/` 目录下，默认使用 `pt/best.pt`。

### 2. 启动主程序

```bash
python main.py
```

Windows 下也可以直接使用当前 Conda 环境解释器：

```powershell
& D:/Anaconda3/envs/yolov5_pyqt5/python.exe "C:/05Projects/Python/orchard-patrol-vision/main.py"
```

### 3. 启动甲方 B 演示

```bat
scripts\run-client-b-demo.bat
```

该脚本会使用 `samples/videos/robot_push/test0_push.mp4`，以甲方 B 模式启动：

- RTMP 推流到甲方 B 平台配置地址
- UDP 上报机器人巡检数据
- 视频正放结束后倒放，倒放结束后继续正放
- 按固定巡检时间轴模拟左右两侧果树 ID 上报

## 双甲方切换

在 `config/app_config.py` 中修改：

```python
# 在这里选择默认配置：'client_a' | 'client_b' | 'both'
ACTIVE_PRESET = "client_b"
```

也可以通过命令行临时指定：

```bash
python main.py --preset client_a
python main.py --preset client_b
python main.py --preset both
```

配置含义：

| 配置         | 说明                                       |
| ------------ | ------------------------------------------ |
| `client_a` | 仅对接甲方 A：HTTP + RTMP                  |
| `client_b` | 仅对接甲方 B：UDP + RTMP                   |
| `both`     | 同时开启 HTTP、UDP、RTMP，主要用于联调测试 |

## 甲方 B 推流与 UDP

甲方 B 当前默认配置：

- RTMP：`rtmp://www.xsjny.com/live/robot1_sensor1`
- UDP：`1.15.149.164:4926`
- UDP 数据包：28 字节二进制协议，包头 `0x66`，包尾 `0x99`

UDP 上报内容包括：

- 机器人 ID
- 机器人状态
- 帧号
- 左/右果树 ID
- 时间
- GPS
- 方向角
- 速度
- 相机高度
- 电池电压
- 电量
- 校验和

## 平台账号

平台登录账号密码不要写进可提交代码。

本地真实凭据请放在：

```text
config/platform_accounts.local.json
```

该文件已被 `.gitignore` 忽略。提交到 GitHub 时保留：

```text
config/platform_accounts.example.json
docs/PLATFORM_ACCOUNTS.md
```

## 常用调试工具

```bash
# 查看模型类别
python tools/check_names.py

# 测试甲方 B UDP 协议
python tools/robot_udp_simulator.py

# 测试 RTMP 推流连通性
python tools/rtmp_probe.py
```

## 注意事项

- 本项目使用 PyQt5 作为桌面界面框架，因此需要在有图形界面的系统会话中运行。
- 开启 RTMP 推流前，请确认系统已安装 FFmpeg。
- `logs/`、`runs/`、`result/` 等运行输出目录不建议提交到 GitHub。
- 大视频、模型权重和本地凭据应继续保持本地管理。
