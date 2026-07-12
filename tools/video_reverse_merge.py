"""
视频正序 + 逆序合并工具
使用 ffmpeg 预先生成正序 + 逆序的视频文件，减少实时推流时的性能开销
"""

import subprocess
import sys
import os
import argparse
from pathlib import Path

# Windows 控制台默认可能是 GBK，统一改成 UTF-8，避免中文/符号输出报错
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ==================== 默认路径配置（可修改） ====================
PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_VIDEO = str(PROJECT_DIR / 'samples' / 'videos' / 'robot_push' / 'test0_push.mp4')           # 输入视频路径
DEFAULT_OUTPUT_VIDEO = str(PROJECT_DIR / 'samples' / 'videos' / 'robot_push' / 'test_forward_reverse.mp4')  # 输出视频路径
# ===============================================================


def check_ffmpeg() -> bool:
    """检查 ffmpeg 是否已安装"""
    try:
        subprocess.run(['ffmpeg', '-version'], 
                      capture_output=True, 
                      check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def get_video_info(video_file: str) -> dict:
    """获取视频文件信息"""
    cmd = [
        'ffprobe',
        '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=duration,width,height,codec_name',
        '-of', 'json',
        video_file
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        import json
        info = json.loads(result.stdout)
        stream = info['streams'][0]
        return {
            'duration': float(stream.get('duration', 0)),
            'width': int(stream.get('width', 0)),
            'height': int(stream.get('height', 0)),
            'codec': stream.get('codec_name', 'unknown')
        }
    except Exception as e:
        print(f"⚠️  无法获取视频信息：{e}")
        return {}


def merge_video_forward_reverse(input_file: str, output_file: str, 
                                keep_audio: bool = True,
                                codec: str = 'libx264',
                                preset: str = 'medium') -> bool:
    """
    合并正序 + 逆序视频
    
    参数:
        input_file: 输入视频文件路径
        output_file: 输出文件路径
        keep_audio: 是否保留音频
        codec: 视频编码格式
        preset: 编码预设（ultrafast/fast/medium/slow）
    """
    if not os.path.exists(input_file):
        print(f"❌ 输入文件不存在：{input_file}")
        return False
    
    # 获取视频信息
    print("📊 分析视频文件...")
    info = get_video_info(input_file)
    if info:
        duration = info.get('duration', 0)
        print(f"   时长：{duration:.2f} 秒")
        print(f"   分辨率：{info.get('width', 0)}x{info.get('height', 0)}")
        print(f"   编码：{info.get('codec', 'unknown')}")
        print(f"   预计输出时长：{duration * 2:.2f} 秒")
    
    # 构建 ffmpeg 命令
    audio_config = 'a=1' if keep_audio else 'a=0'
    
    cmd = [
        'ffmpeg',
        '-i', input_file,
        '-filter_complex',
        f'[0:v]reverse[v1];[0:v][v1]concat=n=2:v=1:{audio_config}[outv]',
        '-map', '[outv]',
    ]
    
    # 音频处理
    if keep_audio:
        cmd.extend([
            '-map', '0:a?',
            '-c:a', 'aac',
            '-b:a', '128k'
        ])
    
    # 视频编码参数
    cmd.extend([
        '-c:v', codec,
        '-preset', preset,
        '-movflags', '+faststart',  # 优化在线播放
    ])
    
    # 输出文件
    cmd.append(output_file)
    
    print(f"\n🎬 开始处理：{os.path.basename(input_file)}")
    print(f"   输出：{os.path.basename(output_file)}")
    print(f"   编码：{codec} ({preset})")
    print(f"   音频：{'保留' if keep_audio else '禁用'}")
    print("-" * 70)
    
    try:
        # 运行 ffmpeg
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        
        # 实时显示进度
        for line in process.stderr:
            if 'time=' in line:
                # 提取时间信息
                parts = line.split('time=')
                if len(parts) > 1:
                    time_str = parts[1].split()[0]
                    print(f"\r   进度：{time_str}", end='', flush=True)
        
        process.wait()
        
        if process.returncode == 0:
            print("\n\n✅ 处理完成！")
            
            # 显示输出文件信息
            output_size = os.path.getsize(output_file) / (1024 * 1024)
            print(f"   输出文件大小：{output_size:.2f} MB")
            return True
        else:
            print("\n\n❌ 处理失败")
            return False
            
    except KeyboardInterrupt:
        print("\n\n⌨️  用户中断")
        process.kill()
        return False
    except Exception as e:
        print(f"\n\n❌ 错误：{e}")
        return False


def batch_process(input_files: list, output_dir: str, **kwargs):
    """批量处理多个视频文件"""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    print(f"\n📦 批量处理 {len(input_files)} 个文件")
    print(f"   输出目录：{output_dir}")
    print("-" * 70)
    
    success_count = 0
    for i, input_file in enumerate(input_files, 1):
        print(f"\n[{i}/{len(input_files)}]")
        
        # 生成输出文件名
        input_name = Path(input_file).stem
        output_file = str(output_path / f"{input_name}_forward_reverse.mp4")
        
        if merge_video_forward_reverse(input_file, output_file, **kwargs):
            success_count += 1
    
    print("\n" + "=" * 70)
    print(f"✅ 批量处理完成：{success_count}/{len(input_files)} 成功")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description='视频正序 + 逆序合并工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用默认路径
  python video_reverse_merge.py
  
  # 单个文件处理
  python video_reverse_merge.py -i input.mp4 -o output.mp4
  
  # 批量处理
  python video_reverse_merge.py -i video1.mp4 video2.mp4 -o ./output/
  
  # 禁用音频（减小文件大小）
  python video_reverse_merge.py -i input.mp4 -o output.mp4 --no-audio
  
  # 快速编码（适合测试）
  python video_reverse_merge.py -i input.mp4 -o output.mp4 --preset ultrafast
        """
    )
    
    # 修改：设置默认值
    parser.add_argument('-i', '--input', nargs='+', default=None,
                       help='输入视频文件路径（支持多个文件，不填则使用默认路径）')
    parser.add_argument('-o', '--output', default=None,
                       help='输出文件路径（单个文件）或目录（批量处理，不填则使用默认路径）')
    parser.add_argument('--no-audio', action='store_true',
                       help='禁用音频输出')
    parser.add_argument('--codec', default='libx264',
                       help='视频编码格式（默认：libx264）')
    parser.add_argument('--preset', default='medium',
                       choices=['ultrafast', 'fast', 'medium', 'slow', 'veryslow'],
                       help='编码预设（默认：medium）')
    
    args = parser.parse_args()
    
    # 检查 ffmpeg
    if not check_ffmpeg():
        print("❌ 未找到 ffmpeg，请先安装 ffmpeg")
        print("   Windows: https://ffmpeg.org/download.html")
        print("   Ubuntu: sudo apt install ffmpeg")
        print("   macOS: brew install ffmpeg")
        sys.exit(1)
    
    # 检查 ffprobe
    try:
        subprocess.run(['ffprobe', '-version'], 
                      capture_output=True, 
                      check=True)
    except:
        print("⚠️  未找到 ffprobe，将跳过视频信息分析")
    
    # 使用默认路径或命令行参数
    input_files = args.input if args.input else [DEFAULT_INPUT_VIDEO]
    output_path = args.output if args.output else DEFAULT_OUTPUT_VIDEO
    
    # 单个文件或批量处理
    if len(input_files) == 1:
        # 单个文件处理
        success = merge_video_forward_reverse(
            input_files[0],
            output_path,
            keep_audio=not args.no_audio,
            codec=args.codec,
            preset=args.preset
        )
        sys.exit(0 if success else 1)
    else:
        # 批量处理
        batch_process(
            input_files,
            output_path,
            keep_audio=not args.no_audio,
            codec=args.codec,
            preset=args.preset
        )


if __name__ == '__main__':
    main()
