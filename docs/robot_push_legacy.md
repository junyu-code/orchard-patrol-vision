# robot_push 迁移说明

原 `robot_push/` 目录已经拆分到正式项目结构中，不再作为业务入口使用。

## 现在的位置

- 正式双甲方入口：`main.py`
- 甲方B演示启动脚本：`scripts/run-client-b-demo.bat`
- 甲方B UDP 发送模块：`transport/udp_sender.py`
- 甲方B UDP 协议：`transport/robot_protocol.py`
- RTMP 推流模块：`transport/rtmp_sender.py`
- 新旧地址备份：`config/endpoints.json`
- 业务视频素材：`samples/videos/robot_push/`
- UDP 独立测试工具：`tools/robot_udp_simulator.py`
- 视频推流独立测试脚本：`tools/test-video-push.bat`
- 正序 + 逆序视频生成工具：`tools/video_reverse_merge.py`

## 保留的旧入口

旧版完整模拟器已经移入 `tools/archive/`，只作为代码备份，不建议继续作为日常入口。

日常运行甲方B演示请使用：

```bat
scripts\run-client-b-demo.bat
```

或直接使用：

```powershell
python main.py --preset client_b --source "samples/videos/robot_push/test0_pingpong.mp4" --auto-start
```
