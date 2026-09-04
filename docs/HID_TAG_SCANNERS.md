# 双路 HID POS 标签扫描器

项目支持两台 Newland EM22/ADL622 以 HID POS 方式读取果树条码。当前固定绑定：

- 左侧：`AB031246`
- 右侧：`AB030000`

绑定依据是 USB 硬件序列号，不依赖 USB 插口或 Windows/Linux 的枚举顺序。

## 设备模式

两台设备必须设置为手册中的纯 `HID POS` 模式。Windows 设备管理器应显示：

- `VID=1EAB`、`PID=0010`
- `POS HID 条形码扫描程序`

不要使用 `USB HID Keyboard` 或 `PID=0022` 的复合键盘模式，否则扫码内容会输入当前获得焦点的窗口。

## 标签格式

默认接受纯数字标签，例如图片中的 `214`，也接受 `TREE:214`、`TREE-214` 和 `TREE_214`。编号范围为 `1` 到 `65535`。

每次扫码会更新对应一侧的树号；默认 3 秒没有再次扫码后该值失效。重复编号在 0.3 秒内只计一次。可通过 `HID_TAG_*` 配置项调整。

## 果树 ID 来源开关

PyQt5 左侧设置区提供“使用二维码识别设备扫描”开关，默认开启；两种状态严格互斥：

- 关闭：果树 ID 只使用下位机遥测值，扫码不会覆盖它。
- 开启：果树 ID 只使用左右 HID POS 扫码值，不读取下位机树号；未扫码、扫码超时或某一侧没有有效扫码时，对应树号为 `0`。

开关在运行中切换后从下一帧起生效，不需要重启任务。Linux 无界面运行可使用等价参数：

```bash
python main.py --headless --tree-id-source hid
python main.py --headless --tree-id-source telemetry
```

## 双路相机固定绑定

界面不再提供相机选择切换。程序固定使用：

- 左路相机：Windows 设备号 `0`，Linux `/dev/video0`
- 右路相机：Windows 设备号 `1`，Linux `/dev/video1`

Windows 的设备号来自 OpenCV 当前枚举顺序；如果重新插拔后顺序变化，可通过环境变量覆盖：

```powershell
$env:CAMERA_LEFT_SOURCE = "0"
$env:CAMERA_RIGHT_SOURCE = "1"
python main.py
```

## 依赖安装

Windows（项目 Conda 环境）：

```powershell
conda activate yolov5_pyqt5
python -m pip install -r requirements.txt
```

Linux：

```bash
python3 -m pip install -r requirements.txt
sudo usermod -aG plugdev "$USER"
```

Linux 使用 `hidapi` 访问 `hidraw`。如果设备能枚举但无法打开，需要增加 udev 规则，重新插拔设备并重新登录：

```text
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="1eab", ATTRS{idProduct}=="0010", MODE="0660", GROUP="plugdev"
```

Windows 通过系统 `Windows.Devices.PointOfService` API 领取 POS 设备，避免键盘接口抢占输入焦点；Linux 直接从 POS HID 输入报告读取。

## 启动自检

程序启动日志应包含：

```text
[HID标签] 左侧设备已由 Windows POS API 领取：AB031246
[HID标签] 右侧设备已由 Windows POS API 领取：AB030000
```

扫码成功时应包含 `左侧扫码：ID0214` 或 `右侧扫码：ID0214`。如果两台扫描器物理方向相反，只需交换 `HID_TAG_LEFT_SERIAL` 和 `HID_TAG_RIGHT_SERIAL` 环境变量，不修改代码。
