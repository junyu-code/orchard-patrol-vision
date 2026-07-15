# 数据来源模式

`DATA_MODE` 是机器人遥测数据的总开关，默认值为 `debug`。摄像头/视频输入和 YOLO 检测结果仍按各自配置运行，不由这个开关伪造。

| 模式 | 真实数据 | 缺失数据 | GPS 串口 | 虚拟果树事件 |
| --- | --- | --- | --- | --- |
| `real` | 逐字段使用真实值 | 保持为空，不回退 | 按配置读取 | 禁止 |
| `debug` | 逐字段优先使用真实值 | 对应字段用虚拟值补齐 | 按配置读取，定位有效时优先 | 允许 |
| `simulation` | 全部忽略 | 全部使用虚拟值 | 不打开 | 允许 |

## 配置开关

默认模式在 `config/app_config.py`：

```python
DATA_MODE = "debug"
```

也可以在启动时覆盖：

```bash
python main.py --data-mode real
python main.py --data-mode debug
python main.py --data-mode simulation
```

Linux 部署脚本支持环境变量，未指定时为 `debug`：

```bash
DATA_MODE=real ./detect.sh
```

甲方 B 的本地演示脚本已显式指定 `simulation`，不会读取或混入现场 GPS 串口数据。

## 缺失值处理

真实模式不会再生成固定北京坐标、24V 电压、85% 电量或零速度等占位数据：

- 界面显示 `--`。
- HTTP JSON 使用 `null` 表示字段不存在，检测结果和图像仍可上报。
- UDP 是固定长度二进制协议，无法表示空值；必需遥测缺失时跳过该数据包，并每 5 秒最多记录一次缺失字段告警。

当前项目的真实串口输入是 OPGPS 定位数据。速度会根据连续有效定位估算并在 UI 中标为黄色估算值；方向、电池、相机高度、路线和路径点还没有真实接收模块，因此它们在 `real` 模式下为空，在 `debug` 模式下由虚拟传感器补齐。
