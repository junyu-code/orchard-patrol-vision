"""
机器人完整模拟器 - 同时进行视频推流和UDP数据发送
支持多机器人同时模拟
"""

import subprocess
import sys
import os
import time
import signal
from pathlib import Path
from typing import List, Optional

# Windows 控制台默认可能是 GBK，统一改成 UTF-8，避免中文/符号输出报错
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_VIDEO_FILE = str(PROJECT_DIR / 'videos' / 'test0.mp4')
DEFAULT_VIDEO_FILE = str(PROJECT_DIR / 'videos' / 'test0_pingpong.mp4')
DEFAULT_UDP_HOST = '1.15.149.164'
DEFAULT_UDP_PORT = 4926
LEGACY_UDP_HOST = '43.139.69.203'
LEGACY_UDP_PORT = 10088

class FrameExtractor:
    """视频帧抽取器"""
    
    def __init__(self, video_file: str, output_dir: str = './frames'):
        self.video_file = video_file
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def extract_at_timestamp(self, timestamp: float, 
                            filename: str = None,
                            format: str = 'jpg') -> Optional[str]:
        """抽取指定时间点的帧"""
        if filename is None:
            filename = f"frame_{timestamp:.3f}.{format}"
        
        output_file = self.output_dir / filename
        
        cmd = [
            'ffmpeg',
            '-y',
            '-ss', str(timestamp),
            '-i', self.video_file,
            '-vframes', '1',
            '-q:v', '2',
            str(output_file)
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, check=True)
            if output_file.exists():
                return str(output_file)
        except Exception as e:
            print(f"❌ 抽帧失败：{e}")
        
        return None
    
    def extract_multiple(self, timestamps: List[float], 
                        prefix: str = 'frame') -> List[str]:
        """批量抽取多个时间点的帧"""
        extracted_files = []
        
        for i, ts in enumerate(timestamps):
            filename = f"{prefix}_{ts:.3f}.jpg"
            result = self.extract_at_timestamp(ts, filename)
            if result:
                extracted_files.append(result)
                print(f"   ✅ 抽取 {ts:.2f}s -> {filename}")
        
        return extracted_files

class RobotSimulatorManager:
    """管理机器人视频推流和UDP数据发送"""
    
    def __init__(self):
        self.processes: List[subprocess.Popen] = []
        self.running = False
        self.frame_extractor: Optional[FrameExtractor] = None
        
    def check_dependencies(self) -> bool:
        """检查依赖项"""
        print("🔍 检查依赖项...")
        
        # 检查ffmpeg
        try:
            subprocess.run(['ffmpeg', '-version'], 
                         capture_output=True, 
                         check=True)
            print("  ✅ ffmpeg 已安装")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("  ❌ 未找到 ffmpeg，请先安装 ffmpeg")
            return False
        
        # 检查SimulateUDP.py
        udp_script = Path(__file__).parent / 'SimulateUDP.py'
        if not udp_script.exists():
            print(f"  ❌ 未找到 SimulateUDP.py: {udp_script}")
            return False
        print("  ✅ SimulateUDP.py 已找到")
        
        # 检查robot_protocol.py
        protocol_script = Path(__file__).parent / 'robot_protocol.py'
        if not protocol_script.exists():
            print(f"  ❌ 未找到 robot_protocol.py: {protocol_script}")
            return False
        print("  ✅ robot_protocol.py 已找到")
        
        return True
    
    def start_udp_simulator(
        self,
        robot_id: int,
        robot_status: int,
        server_ip: str,
        server_port: int,
        tree_interval: int = 8,
        tree_jitter: int = 2,
    ) -> subprocess.Popen:
        """启动UDP数据模拟器"""
        udp_script = Path(__file__).parent / 'SimulateUDP.py'
        
        cmd = [
            sys.executable,
            str(udp_script),
            str(robot_id),
            str(robot_status),  # 机器人状态（0=关机,1=巡检,2=充电,255=故障）
            server_ip,
            str(server_port),
            '0',  # duration=0表示持续运行
            '1.0',  # interval=1秒
            str(tree_interval),
            str(tree_jitter),
        ]
        
        print(f"  📡 启动UDP模拟器: robot{robot_id}, status={robot_status}")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        
        return process
    
    def start_video_stream(self, video_file: str, stream_url: str, 
                          transport: str = 'tcp') -> subprocess.Popen:
        """启动视频推流"""
        if not os.path.exists(video_file):
            raise FileNotFoundError(f"视频文件不存在: {video_file}")
        
        # 构建ffmpeg命令
        cmd = [
            'ffmpeg',
            '-re',                          # 实时速率
            '-stream_loop', '-1',           # 循环播放
            '-i', video_file,               # 输入文件
            '-vf', 'scale=640:-2,fps=15',   # 降低分辨率和帧率，适配低带宽测试服务器
            '-c:v', 'libx264',              # 视频编码
            '-preset', 'veryfast',          # 兼顾低延迟和压缩效率
            '-tune', 'zerolatency',         # 零延迟优化
            '-b:v', '700k',                 # 控制视频平均码率
            '-maxrate', '900k',             # 限制码率峰值，避免平台入口拥塞
            '-bufsize', '1400k',            # 配合 maxrate 平滑码率波动
            '-g', '30',                     # 15fps 下约 2 秒一个关键帧
            '-an',                          # 当前业务不需要音频，减少带宽占用
        ]
        
        # 根据协议类型添加参数
        if 'rtsp' in stream_url.lower():
            cmd.extend([
                '-rtsp_transport', transport,
                '-f', 'rtsp',
                stream_url
            ])
        elif 'rtmp' in stream_url.lower():
            cmd.extend([
                '-f', 'flv',
                stream_url
            ])
        else:
            raise ValueError(f"不支持的流媒体协议: {stream_url}")
        
        print(f"  📹 启动视频推流: {stream_url}")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        return process

    def prepare_default_video(self) -> str:
        """返回默认 ping-pong 视频路径。"""
        output_video = Path(DEFAULT_VIDEO_FILE)
        if not output_video.exists():
            raise FileNotFoundError(f"默认视频不存在: {output_video}")
        return str(output_video)
    
    def simulate_robot(self, robot_id: int, robot_status: int,
                      video_file: str, orchard_id: str,
                      server_ip: str = '127.0.0.1',
                      rtsp_port: int = 8554,
                      udp_port: int = 5006,
                      transport: str = 'tcp',
                      start_video: bool = True,
                      tree_interval: int = 8,
                      tree_jitter: int = 2):
        """
        模拟单个机器人的完整数据推流
        
        参数:
            robot_id: 机器人ID (1=robotA, 2=robotB, 3=robotC)
            robot_status: 机器人状态 (0=关机,1=巡检,2=充电,255=故障)
            video_file: 视频文件路径
            orchard_id: 果园ID
            server_ip: 服务器IP地址
            rtsp_port: RTSP端口
            udp_port: UDP端口
            transport: 传输协议 (tcp/udp)
        """
        robot_names = {1: 'robotA', 2: 'robotB', 3: 'robotC'}
        robot_status_names = {0: 'shutdown', 1: 'patrolling', 2: 'charging', 255: 'fault'}
        
        robot_name = robot_names.get(robot_id, f'robot{robot_id}')
        status_name = robot_status_names.get(robot_status, 'unknown')
        
        print(f"\n{'='*70}")
        print(f"启动机器人模拟: {robot_name} - 状态: {status_name}")
        print(f"{'='*70}")
        
        # 构建RTSP URL
        stream_url = f"rtsp://{server_ip}:{rtsp_port}/live/{orchard_id}/{robot_name}"
        
        try:
            # 启动UDP模拟器
            udp_process = self.start_udp_simulator(
                robot_id,
                robot_status,
                server_ip,
                udp_port,
                tree_interval=tree_interval,
                tree_jitter=tree_jitter,
            )
            self.processes.append(udp_process)
            
            # 等待UDP模拟器启动
            time.sleep(1)
            
            if start_video:
                # 启动视频推流
                video_process = self.start_video_stream(video_file, stream_url, transport)
                self.processes.append(video_process)
            
            print(f"  ✅ {robot_name} 启动成功")
            print(f"     UDP: {server_ip}:{udp_port}")
            print(f"     RTSP: {stream_url}" if start_video else "     Video: disabled")
            
        except Exception as e:
            print(f"  ❌ 启动失败: {e}")
            self.stop_all()
            raise
    
    def simulate_multiple_robots(self, configs: List[dict]):
        """
        同时模拟多个机器人
        
        参数:
            configs: 机器人配置列表，每个配置包含:
                - robot_id: 机器人ID
                - robot_status: 机器人状态
                - video_file: 视频文件路径
                - orchard_id: 果园ID
                - server_ip: 服务器IP (可选)
                - transport: 传输协议 (可选)
        """
        print(f"\n{'='*70}")
        print(f"准备启动 {len(configs)} 个机器人模拟")
        print(f"{'='*70}")
        
        for i, config in enumerate(configs, 1):
            print(f"\n[{i}/{len(configs)}] ", end='')
            self.simulate_robot(**config)
            time.sleep(0.5)  # 短暂延迟，避免同时启动过多进程
        
        print(f"\n{'='*70}")
        print(f"✅ 所有机器人已启动")
        print(f"{'='*70}")
    
    def monitor_processes(self):
        """监控进程状态（逻辑不变）"""
        self.running = True
        print("\n📊 监控进程状态 (按 Ctrl+C 停止)")
        print("-" * 70)
        
        try:
            while self.running:
                time.sleep(5)
                
                # 检查进程状态
                active_count = 0
                for process in self.processes:
                    if process.poll() is None:
                        active_count += 1
                
                print(f"[{time.strftime('%H:%M:%S')}] 活动进程: {active_count}/{len(self.processes)}")
                
                # 如果所有进程都结束了，退出监控
                if active_count == 0:
                    print("\n⚠️ 所有进程已结束")
                    break
                    
        except KeyboardInterrupt:
            print("\n\n⌨️  收到中断信号，正在停止所有进程...")
            self.stop_all()
    
    def stop_all(self):
        """停止所有进程"""
        self.running = False
        
        if not self.processes:
            return
        
        print(f"\n🛑 停止 {len(self.processes)} 个进程...")
        
        for i, process in enumerate(self.processes, 1):
            try:
                if process.poll() is None:  # 进程还在运行
                    print(f"  [{i}/{len(self.processes)}] 停止进程 PID={process.pid}")
                    process.terminate()
                    
                    # 等待进程结束，最多等待3秒
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        print(f"    ⚠️ 进程未响应，强制终止")
                        process.kill()
                        
            except Exception as e:
                print(f"    ❌ 停止进程失败: {e}")
        
        self.processes.clear()
        print("  ✅ 所有进程已停止")
def setup_frame_extractor(self, video_file: str, 
                             output_dir: str = './frames'):
    """设置帧抽取器"""
    self.frame_extractor = FrameExtractor(video_file, output_dir)
    print(f"📸 帧抽取器已就绪：{output_dir}")

def extract_and_send_frames(self, timestamps: List[float],
                            udp_ip: str, udp_port: int,
                            prefix: str = 'frame'):
    """抽取帧并通过 UDP 发送"""
    if not self.frame_extractor:
        print("❌ 未设置帧抽取器")
        return
    
    print(f"\n📸 开始抽取 {len(timestamps)} 帧...")
    files = self.frame_extractor.extract_multiple(timestamps, prefix)
    
    # 这里可以添加 UDP 发送逻辑
    for file_path in files:
        self._send_file_via_udp(file_path, udp_ip, udp_port)

def _send_file_via_udp(self, file_path: str, ip: str, port: int):
    """通过 UDP 发送文件"""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    try:
        with open(file_path, 'rb') as f:
            data = f.read()
            sock.sendto(data, (ip, port))
            print(f"   📤 已发送：{os.path.basename(file_path)}")
    except Exception as e:
        print(f"   ❌ 发送失败：{e}")
    finally:
        sock.close()

def interactive_mode():
    """交互式配置模式"""
    print("\n" + "="*70)
    print("  机器人模拟器 - 交互式配置")
    print("="*70)
    
    manager = RobotSimulatorManager()
    
    # 检查依赖
    if not manager.check_dependencies():
        return
    
    print("\n" + "-"*70)
    
    # 配置机器人
    print("\n📋 配置机器人参数:")
    print()
    
    # 1. 机器人ID
    robot_choice = input("1. 选择机器人 [1=robotA, 2=robotB, 3=robotC] (默认=1): ").strip()
    robot_id = int(robot_choice) if robot_choice else 1
    
    # 2. 机器人状态（新增）
    print("\n2. 选择机器人状态:")
    print("   [0] 关机/停止运行")
    print("   [1] 正在巡检（推荐）")
    print("   [2] 充电状态")
    print("   [255] 故障需检修")
    status_choice = input("   请选择 (默认=1): ").strip()
    robot_status = int(status_choice) if status_choice else 1
    
    # 3. 果园ID
    orchard_id = input("\n3. 果园ID (默认=orchard1): ").strip() or "orchard1"
    
    # 4. 服务器IP
    server_ip = input("4. 服务器IP (默认=127.0.0.1): ").strip() or "127.0.0.1"
    
    # 5. 视频文件路径
    start_video_choice = input("\n5. 是否启动本地默认视频? [Y/n]: ").strip().lower()
    start_video = start_video_choice != 'n'

    video_file = DEFAULT_VIDEO_FILE
    transport = 'tcp'
    if start_video:
        if not os.path.exists(DEFAULT_VIDEO_FILE):
            video_file = manager.prepare_default_video()
        video_file = input(f"\n6. 视频文件路径 (默认={video_file}): ").strip() or video_file
        if not os.path.exists(video_file):
            print(f"❌ 错误: 视频文件不存在: {video_file}")
            return

        print("\n7. 选择传输协议:")
        print("   [1] RTSP + TCP (推荐)")
        print("   [2] RTSP + UDP")
        transport_choice = input("   请选择 (默认=1): ").strip()
        transport = 'udp' if transport_choice == '2' else 'tcp'
    
    # 确认配置
    print("\n" + "-"*70)
    print("📝 配置确认:")
    status_names = {0: '关机', 1: '巡检', 2: '充电', 255: '故障'}
    print(f"   机器人: robot{robot_id}")
    print(f"   状态: {status_names.get(robot_status, '未知')}")
    print(f"   果园: {orchard_id}")
    print(f"   服务器: {server_ip}")
    print(f"   视频: {video_file if start_video else '不启动'}")
    print(f"   协议: RTSP + {transport.upper()}" if start_video else "   协议: 仅 UDP")
    print("-"*70)
    
    confirm = input("\n确认启动? [Y/n]: ").strip().lower()
    if confirm == 'n':
        print("❌ 已取消")
        return
    
    # 启动模拟
    try:
        manager.simulate_robot(
            robot_id=robot_id,
            robot_status=robot_status,
            video_file=video_file,
            orchard_id=orchard_id,
            server_ip=server_ip,
            transport=transport,
            start_video=start_video
        )
        
        manager.monitor_processes()
        
    except KeyboardInterrupt:
        print("\n\n⌨️  收到中断信号")
    finally:
        manager.stop_all()


def batch_mode_example():
    """批量模式示例 - 同时模拟多个机器人"""
    manager = RobotSimulatorManager()
    
    # 检查依赖
    if not manager.check_dependencies():
        return
    
    # 配置多个机器人
    configs = [
        {
            'robot_id': 1,
            'robot_status': 1,  # 巡检状态
            #TODO
            'video_file': DEFAULT_VIDEO_FILE,
            'orchard_id': 'orchard1',
            'server_ip': '127.0.0.1',
            'transport': 'tcp',
            'start_video': True
        },
        {
            'robot_id': 2,
            'robot_status': 2,  # 充电状态
            #TODO
            'video_file': DEFAULT_VIDEO_FILE,
            'orchard_id': 'orchard1',
            'server_ip': '127.0.0.1',
            'transport': 'tcp',
            'start_video': True
        },
    ]
    
    try:
        manager.simulate_multiple_robots(configs)
        manager.monitor_processes()
    except KeyboardInterrupt:
        print("\n\n⌨️  收到中断信号")
    finally:
        manager.stop_all()


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='机器人完整模拟器 - 同时进行视频推流和UDP数据发送',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 交互式模式
  python robot_simulator_all.py
  
  # 命令行模式
  python robot_simulator_all.py --robot-id 1 --status 1 --auto-video --orchard orchard1
  
  # 批量模式（需要修改代码中的batch_mode_example函数）
  python robot_simulator_all.py --batch
        """
    )
    
    # 调整命令行参数：移除--sensor-id，新增--status
    parser.add_argument('--robot-id', type=int, help='机器人ID (1=robotA, 2=robotB, 3=robotC)')
    parser.add_argument('--status', type=int, default=1, help='机器人状态 (0=关机,1=巡检,2=充电,255=故障，默认=1)')
    parser.add_argument('--video', type=str, help='视频文件路径')
    parser.add_argument('--orchard', type=str, default='orchard1', help='果园ID (默认: orchard1)')
    parser.add_argument('--server-ip', type=str, default=DEFAULT_UDP_HOST, help=f'UDP服务器IP (默认: {DEFAULT_UDP_HOST})')
    parser.add_argument('--rtsp-port', type=int, default=8554, help='RTSP端口 (默认: 8554)')
    parser.add_argument('--udp-port', type=int, default=DEFAULT_UDP_PORT, help=f'UDP端口 (默认: {DEFAULT_UDP_PORT})')
    parser.add_argument('--transport', type=str, default='tcp', choices=['tcp', 'udp'], 
                       help='传输协议 (默认: tcp)')
    parser.add_argument('--auto-video', action='store_true', help='使用默认自然 ping-pong 视频')
    parser.add_argument('--no-video', action='store_true', help='只启动 UDP，不启动视频推流')
    parser.add_argument('--tree-interval', type=int, default=8, help='检测到果树的基础间隔帧数/秒数 (默认: 8)')
    parser.add_argument('--tree-jitter', type=int, default=2, help='果树检测间隔波动范围 (默认: ±2)')
    parser.add_argument('--batch', action='store_true', help='批量模式（同时模拟多个机器人）')
    
    args = parser.parse_args()
    
    # 批量模式
    if args.batch:
        print("🚀 批量模式 - 同时模拟多个机器人（新协议版）")
        print("⚠️  请修改 batch_mode_example() 函数中的配置")
        batch_mode_example()
        return
    
    # 命令行模式
    if args.robot_id and (args.video or args.auto_video or args.no_video):
        manager = RobotSimulatorManager()
        
        if not manager.check_dependencies():
            sys.exit(1)
        
        try:
            video_file = args.video
            start_video = not args.no_video
            if args.auto_video:
                video_file = manager.prepare_default_video()

            manager.simulate_robot(
                robot_id=args.robot_id,
                robot_status=args.status,
                video_file=video_file or DEFAULT_VIDEO_FILE,
                orchard_id=args.orchard,
                server_ip=args.server_ip,
                rtsp_port=args.rtsp_port,
                udp_port=args.udp_port,
                transport=args.transport,
                start_video=start_video,
                tree_interval=args.tree_interval,
                tree_jitter=args.tree_jitter,
            )
            
            manager.monitor_processes()
            
        except KeyboardInterrupt:
            print("\n\n⌨️  收到中断信号")
        finally:
            manager.stop_all()
    else:
        # 交互式模式
        interactive_mode()


if __name__ == '__main__':
    main()
