# orchard-patrol-vision 项目结构

## 入口和核心代码

- `main.py`：主程序入口，包含界面交互、病虫害识别线程、HTTP/UDP 上报、RTMP 推流等逻辑。
- `docs/SYSTEM_FLOW.md`：系统运行流程图，包含总体流程、模块关系和检测线程时序。
- `detect.py`：YOLOv5 命令行检测脚本，偏原版 YOLOv5 用法。
- `train.py` / `val.py` / `export.py`：训练、验证和模型导出脚本。
- `main_win/`：主窗口 UI、实时遥测面板格式化和本地录像模块。
- `dialog/`：RTSP 输入弹窗相关 UI 和逻辑。

## 模型、配置和资源

- `pt/`：项目使用的模型权重目录，默认权重为 `pt/best.pt`。
- `models/`：YOLOv5 网络结构和模型定义。
- `utils/`：YOLOv5 工具函数、数据加载、绘图、日志和辅助模块。
- `config/`：运行配置和对接地址备份，例如 `app_config.py`、`endpoints.json`、`platform_accounts.example.json`、置信度、IoU、RTSP 地址、上次打开目录。
- `icon/`：Qt 资源引用的图标和背景图，不能随意移动。
- `apprcc.qrc` / `apprcc_rc.py`：Qt 资源清单和编译后的资源文件。

## 数据、样例和输出

- `data/`：YOLOv5 数据集配置、示例图片和下载脚本。
- `samples/`：整理后的本地样例图片、视频和演示素材；第二套业务视频统一放在 `samples/videos/robot_push/`。
- `runs/`：YOLOv5 检测或训练输出目录，可删除后自动生成。
- `result/`：界面检测结果保存目录，可删除后自动生成。
- `logs/`：运行日志目录。

## 辅助和实验代码

- `transport/`：正式业务传输模块，包括统一电控遥测、旧 OPGPS、数据模式、甲方A HTTP、甲方B UDP、RTMP 推流和虚拟传感器。
- `serial_utils/`：旧版串口/TCP 辅助模块，和 `transport/` 有部分功能重叠。
- `tools/check_names.py`：查看 `pt/best.pt` 中类别名称的辅助脚本。
- `tools/robot_udp_simulator.py`：甲方B UDP 独立测试工具。
- `tools/video_reverse_merge.py`：生成正序 + 逆序合并视频的工具；当前甲方B演示已支持运行时正放/倒放循环，通常不需要预生成。
- `tools/serial_self_test.py`：统一遥测、旧 OPGPS、回环和双 USB-TTL 串口自测工具。
- `tools/test-video-push.bat`：独立 RTSP/RTMP 推流测试脚本。
- `tools/archive/`：旧版机器人推流完整入口备份，不再作为正式入口。
- `scripts/run-client-b-demo.bat`：甲方B 本地演示启动脚本，使用 `test0_push.mp4` 正放/倒放循环，并按固定秒点通过 UDP 上报果树 ID。
- `experiments/T.py`：基于 ultralytics 新接口的实验界面脚本，不是当前主入口。
- `test.py`：PyQt 多线程实验脚本，不是当前主入口。
- `detect.sh`：Linux 部署启动脚本。

## 建议

- 平时运行优先使用 `python main.py`。
- 模型权重统一放入 `pt/`，不要再放在根目录。
- 检测结果、日志、缓存和大视频文件不要提交到版本库。
- `test.py` 被 YOLOv5 的 W&B sweep 代码引用，暂时保留在根目录。
