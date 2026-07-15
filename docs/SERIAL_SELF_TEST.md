# 串口检查与自测

项目当前有两个正式串口模块：

- `transport/gps_serial_receiver.py`：后台接收以换行结尾的 OPGPS V1 文本报文，负责校验、断线重连和数据失效判断。
- `transport/serial_sender.py`：辅助输出模块，向 STM32 发送 4 字节病害帧，格式为 `FF 病害ID 疑似度 FE`。

当前现场主链路是 GPS 串口接收，行为对应 `/home/rm/gps/gps_receive.py`；项目内的 `GpsSerialReceiver` 在此基础上增加了校验和、分包/粘包、断线重连、过期判断和线程安全快照。

`serial_utils/serial_sender.py` 是未被主程序引用的旧副本，不作为正式维护入口。

## 检查结论

- GPS 接收模块已有报文校验、分包/粘包处理、超时失效、自动探测和断线重连，并有模拟串口单元测试。
- 病害发送模块原先不检查短写，连接失败后主程序仍会显示打开成功；这些问题已经修复。
- `main.py` 当前只初始化病害发送器，检测循环尚未调用 `pack_and_send()`。在定义病害 ID 映射、发送触发条件和限频策略前，开启 `ENABLE_SERIAL` 不会自动上报检测结果。
- 病害帧没有长度、校验和或转义，且数据字节本身可能等于 `FF`/`FE`。STM32 端至少要按固定 4 字节状态机解析并校验尾字节；需要抗干扰时应由两端共同升级协议。

## 1. 无硬件回环自测

下面的命令使用 pyserial 的内存回环端口，发送项目真实病害帧并逐字节回读校验：

```bash
python tools/serial_self_test.py loopback
```

命令返回码为 `0` 表示全部通过，`1` 表示收发内容不一致，`2` 表示端口或参数错误。

## 2. 物理串口回环自测

先停止占用该端口的主程序，在 USB 转串口模块上短接 TX 和 RX，再执行：

```bash
python tools/serial_self_test.py loopback --port /dev/ttyUSB0 --baudrate 9600 --count 5
```

Windows 示例：

```powershell
python tools/serial_self_test.py loopback --port COM13 --baudrate 9600 --count 5
```

物理回环只验证本机串口、线缆和项目报文字节，不能代替 STM32 端协议解析测试。连接外部设备前需确认双方电平兼容，不能把 RS-232 电平直接接到 TTL 串口。

## 3. GPS 接收自测

连接持续发送 OPGPS V1 报文的设备后执行：

```bash
python tools/serial_self_test.py gps --port /dev/ttyGPS_IN --baudrate 9600 --duration 10
```

也可以让工具枚举端口并查找第一个能产生合法 OPGPS 报文的设备：

```bash
python tools/serial_self_test.py gps --port AUTO --duration 15
```

成功时会打印机器人 ID、序号、经纬度、定位质量和卫星数，并汇总协议错误、校验错误、读取错误和连接失败次数。

## 4. 双 USB 串口快速测试

两只 USB-TTL 需要交叉连接并共地：

```text
USB0 TX -> USB1 RX
USB0 RX <- USB1 TX
USB0 GND --- USB1 GND
```

先停止占用 GPS 串口的主程序，然后执行：

```bash
systemctl stop yolo-detect.service
python tools/quick_gps_receive_test.py
systemctl start yolo-detect.service
```

脚本默认把 `/dev/ttyUSB0` 作为模拟发送端，把 `/dev/ttyUSB1` 作为项目接收端。它先完成两个方向的物理字节校验，再由模拟端发送 5 条 OPGPS 报文，通过项目 `GpsSerialReceiver` 接收和解析。成功返回 `0`，链路不通返回 `1`，设备缺失或被其他进程占用返回 `2`。

端口编号不同时可以覆盖默认值：

```bash
python tools/quick_gps_receive_test.py \
  --sender-port /dev/ttyUSB2 \
  --receiver-port /dev/ttyUSB3
```

两只没有唯一序列号的同型号 CH340 不应共用基于 VID/PID 的 udev 别名。它们可能同时命中 `/dev/ttyGPS_IN`，导致该别名随插拔顺序切换；应按 USB 物理路径分别创建稳定别名。

## 5. 端口与权限检查

列出 pyserial 当前可见的物理端口：

```bash
python tools/serial_self_test.py list
```

Ubuntu 出现 `Permission denied` 时，将运行用户加入 `dialout` 组，然后重新登录：

```bash
sudo usermod -aG dialout "$USER"
```

固定部署建议用 udev 创建稳定别名（例如 `/dev/ttyGPS_IN`），不要依赖可能随插拔变化的 `/dev/ttyUSB0` 编号。
