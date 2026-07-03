# 视频流与机器人遥测联调包

这是一个独立联调包，用于复刻“视频 RTMP 推流 + UDP 机器人遥测上报”的完整流程。

包内只包含联调所需内容，不包含 GUI、YOLO、模型权重或其他业务系统接口。

## 目录结构

```text
robot_stream_telemetry_demo/
├── media/
│   └── patrol_demo.mp4
├── README.md
├── requirements.txt
├── run_robot_stream_demo.bat
└── run_robot_stream_demo.py
```

其中 `media/patrol_demo.mp4` 是默认演示视频，程序启动后会读取该视频、推送 RTMP，并同步发送 UDP 遥测数据。

## 环境要求

需要 Python、OpenCV、NumPy，并且本机能直接执行 `ffmpeg`。

```powershell
pip install -r requirements.txt
```

## 默认运行

```powershell
python run_robot_stream_demo.py
```

或者在 Windows 下双击/执行：

```powershell
.\run_robot_stream_demo.bat
```

默认参数：

- 视频源：`media/patrol_demo.mp4`
- RTMP：`rtmp://www.xsjny.com/live/robot1_sensor1`
- UDP：`1.15.149.164:4926`
- UDP 格式：`orchard1|` + 28 字节机器人遥测包
- GPS 起点：`25.28, 110.34`
- 推流参数：`480宽 / 10fps / 400k`

## 指定接收地址

```powershell
python run_robot_stream_demo.py --udp-host 127.0.0.1 --udp-port 5006 --rtmp-url rtmp://127.0.0.1/live/robot1_sensor1
```

如果接收端只需要裸 28 字节 UDP 包，不需要 `orchard1|` 前缀：

```powershell
python run_robot_stream_demo.py --no-orchard-prefix
```

## 常用参数

```powershell
python run_robot_stream_demo.py `
  --source media/patrol_demo.mp4 `
  --rtmp-url rtmp://www.xsjny.com/live/robot1_sensor1 `
  --udp-host 1.15.149.164 `
  --udp-port 4926 `
  --latitude 25.28 `
  --longitude 110.34 `
  --max-width 480 `
  --fps 10 `
  --bitrate 400k
```

## UDP 数据格式

默认发送格式：

```text
orchard1| + 28字节机器人遥测包
```

28 字节遥测包结构：

| 字节 | 字段 |
|---:|---|
| 0 | 包头 `0x66` |
| 1 | robotCode / robot_id |
| 2 | robotStatus，`0=移动`，`1=靠近树/拍照` |
| 3-4 | frameIndex，大端序 |
| 5-6 | leftTreeCode，大端序 |
| 7-8 | rightTreeCode，大端序 |
| 9-11 | hour / minute / second |
| 12-15 | 纬度：度、分、秒、方向 |
| 16-19 | 经度：度、分、秒、方向 |
| 20-21 | azimuth，大端序 |
| 22 | velocity，单位 `0.1m/s` |
| 23 | eyePointHeight，单位 `0.01m` |
| 24 | batVoltage，单位 `0.1V` |
| 25 | soc，单位 `%` |
| 26 | 校验和，`sum(packet[1:26]) & 0xFF` |
| 27 | 包尾 `0x99` |
