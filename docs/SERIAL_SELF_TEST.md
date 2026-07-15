# 串口检查与自测

项目当前保留三类串口能力：

- `transport/telemetry_serial_receiver.py`：正式接收 58 字节 OP-Telemetry V1 电控遥测。
- `transport/gps_serial_receiver.py`：兼容接收旧 OPGPS V1 文本定位报文。
- `transport/serial_sender.py`：保留的 4 字节病害帧辅助发送器，当前主流程不向电控发送。

统一遥测接收器负责帧头、版本、类型、长度、CRC16、帧尾、字段范围、拆包、粘包、序号、超时和自动重连。电控速度有效时直接使用；速度字段缺失时才根据连续 GPS 坐标估算。

## 1. 统一遥测无硬件回环

使用 pyserial 内存回环生成并解析正式 58 字节遥测包：

```bash
python tools/serial_self_test.py telemetry-loopback
```

Windows 项目环境示例：

```powershell
& D:/Anaconda3/envs/yolov5_pyqt5/python.exe tools/serial_self_test.py telemetry-loopback
```

返回码 `0` 表示全部通过，`1` 表示收发或解析不一致，`2` 表示依赖、端口或参数错误。

## 2. 统一遥测现场监听

Linux：

```bash
python tools/serial_self_test.py telemetry \
  --port /dev/ttyTELEMETRY_IN \
  --baudrate 9600 \
  --duration 10
```

Windows：

```powershell
python tools/serial_self_test.py telemetry --port COM13 --baudrate 9600 --duration 10
```

工具会打印包序号、机器人状态、当前/左右果树编号、速度和电量，并汇总 CRC、协议、连接和读取错误。

## 3. 物理串口回环

停止占用端口的主程序，在 USB 转串口模块上短接 TX 和 RX：

```bash
python tools/serial_self_test.py telemetry-loopback \
  --port /dev/ttyUSB0 \
  --baudrate 9600 \
  --count 5
```

Windows 示例：

```powershell
python tools/serial_self_test.py telemetry-loopback --port COM13 --count 5
```

物理回环只验证本机串口、线缆和报文字节，不能代替电控端协议解析测试。连接前必须确认双方电平兼容，禁止把 RS-232 电平直接连接到 TTL UART。

## 4. 双 USB-TTL 联调

两只 USB-TTL 交叉连接并共地：

```text
USB0 TX -> USB1 RX
USB0 RX <- USB1 TX
USB0 GND --- USB1 GND
```

执行：

```bash
python tools/serial_self_test.py dual \
  --sender-port /dev/ttyUSB0 \
  --receiver-port /dev/ttyUSB1
```

该命令依次验证：

1. USB0 到 USB1 的物理字节传输。
2. USB1 到 USB0 的反向物理字节传输。
3. 58 字节统一遥测正式接收链路。
4. 旧 OPGPS 兼容接收链路。

只测试线路时增加：

```bash
--skip-telemetry --skip-opgps
```

## 5. 旧 OPGPS 兼容测试

监听旧 GPS 设备：

```bash
python tools/serial_self_test.py gps --port /dev/ttyGPS_IN --duration 10
```

自动枚举端口：

```bash
python tools/serial_self_test.py gps --port AUTO --duration 15
```

原有双 USB OPGPS 快速脚本继续保留：

```bash
python tools/quick_gps_receive_test.py
```

## 6. 旧病害帧辅助回环

当前业务不要求视觉端向电控返回数据，但辅助发送器仍可独立自测：

```bash
python tools/serial_self_test.py loopback
```

该命令测试旧格式 `FF 病害ID 疑似度 FE`，不代表统一遥测接收协议。

## 7. 端口与权限

列出当前物理串口：

```bash
python tools/serial_self_test.py list
```

Ubuntu 出现 `Permission denied` 时：

```bash
sudo usermod -aG dialout "$USER"
```

执行后重新登录。固定部署建议通过 udev 创建 `/dev/ttyTELEMETRY_IN` 等稳定别名，不要依赖可能随插拔变化的 `/dev/ttyUSB0`。
