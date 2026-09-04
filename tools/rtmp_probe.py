"""RTMP 推流诊断工具。

用途：
1. 按不同分辨率、帧率、码率短时间推流，观察平台能否接收。
2. 每档推流后用 ffprobe 从同一个 RTMP 地址拉流，确认服务器是否真的发布了流。
3. 将完整过程写入 logs/rtmp_probe_*.log，方便和甲方平台日志对照。
"""

import argparse
import datetime as dt
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_VIDEO = ROOT_DIR / "samples" / "videos" / "robot_push" / "test0_push.mp4"
DEFAULT_RTMP_URL = "rtmp://gl.xsjny.com/live/robot1_sensor2"
LOG_DIR = ROOT_DIR / "logs"

PROFILES = [
    {
        "name": "360p_15fps_500k",
        "width": 640,
        "height": 360,
        "fps": 15,
        "bitrate": "500k",
        "maxrate": "650k",
        "bufsize": "1000k",
    },
    {
        "name": "360p_15fps_700k",
        "width": 640,
        "height": 360,
        "fps": 15,
        "bitrate": "700k",
        "maxrate": "900k",
        "bufsize": "1400k",
    },
    {
        "name": "480p_15fps_900k",
        "width": 854,
        "height": 480,
        "fps": 15,
        "bitrate": "900k",
        "maxrate": "1200k",
        "bufsize": "1800k",
    },
    {
        "name": "540p_20fps_1200k",
        "width": 960,
        "height": 540,
        "fps": 20,
        "bitrate": "1200k",
        "maxrate": "1500k",
        "bufsize": "2400k",
    },
    {
        "name": "720p_25fps_1800k",
        "width": 1280,
        "height": 720,
        "fps": 25,
        "bitrate": "1800k",
        "maxrate": "2200k",
        "bufsize": "3600k",
    },
    {
        "name": "720p_30fps_3000k",
        "width": 1280,
        "height": 720,
        "fps": 30,
        "bitrate": "3000k",
        "maxrate": "3600k",
        "bufsize": "6000k",
    },
    {
        "name": "1080p_25fps_4500k",
        "width": 1920,
        "height": 1080,
        "fps": 25,
        "bitrate": "4500k",
        "maxrate": "5400k",
        "bufsize": "9000k",
    },
]


def write_log(log_file, message=""):
    """同时输出到控制台和日志文件。"""
    print(message)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(message + "\n")


def run_command(command, log_file, timeout=None):
    """运行命令并把 stdout/stderr 合并写入日志。"""
    start_time = time.time()
    with log_file.open("a", encoding="utf-8") as f:
        f.write("\n$ " + " ".join(command) + "\n")
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        output_lines = []
        try:
            for line in process.stdout:
                line = line.rstrip()
                output_lines.append(line)
                f.write(line + "\n")
                f.flush()
            return_code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            return_code = -1
            line = f"[TIMEOUT] 命令超过 {timeout} 秒未结束，已终止"
            output_lines.append(line)
            f.write(line + "\n")
        elapsed = time.time() - start_time
        f.write(f"[EXIT] return_code={return_code}, elapsed={elapsed:.1f}s\n")
    return return_code, "\n".join(output_lines)


def build_ffmpeg_command(video, url, profile, duration, ffmpeg):
    """构造单档推流命令。"""
    key_interval = max(1, int(profile["fps"]) * 2)
    return [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "info",
        "-re",
        "-stream_loop",
        "-1",
        "-t",
        str(duration),
        "-i",
        str(video),
        "-vf",
        f"scale={profile['width']}:{profile['height']},fps={profile['fps']}",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-tune",
        "zerolatency",
        "-pix_fmt",
        "yuv420p",
        "-b:v",
        profile["bitrate"],
        "-maxrate",
        profile["maxrate"],
        "-bufsize",
        profile["bufsize"],
        "-g",
        str(key_interval),
        "-f",
        "flv",
        url,
    ]


def build_ffprobe_command(url, ffprobe, timeout_seconds):
    """构造拉流验证命令，Windows 下 rw_timeout 单位是微秒。"""
    return [
        ffprobe,
        "-hide_banner",
        "-loglevel",
        "info",
        "-rw_timeout",
        str(timeout_seconds * 1000000),
        "-show_streams",
        "-select_streams",
        "v:0",
        url,
    ]


def has_video_stream(ffprobe_output):
    """根据 ffprobe 输出粗略判断是否拉到了视频流。"""
    markers = ("codec_name=h264", "codec_type=video", "Video: h264")
    return any(marker in ffprobe_output for marker in markers)


def explain_result(push_code, probe_code, probe_output):
    """给出人能看懂的诊断结论。"""
    if push_code != 0:
        return "推流进程异常退出：优先看日志中的 Connection、timeout、Broken pipe、Server error。"
    if probe_code == 0 and has_video_stream(probe_output):
        return "RTMP 服务器可拉到视频流：如果平台页面仍看不到，重点查平台前端订阅、流名绑定、机器人在线状态或 UDP 数据联动。"
    return "推流命令结束但 ffprobe 拉不到视频：重点查 RTMP 地址/流名、平台是否允许该推流码、服务器发布延迟或网络出口限制。"


def parse_profile_names(value):
    """解析 --profiles 参数。"""
    requested = [item.strip() for item in value.split(",") if item.strip()]
    profile_map = {profile["name"]: profile for profile in PROFILES}
    unknown = [name for name in requested if name not in profile_map]
    if unknown:
        valid = ", ".join(profile_map)
        raise argparse.ArgumentTypeError(f"未知档位：{', '.join(unknown)}。可选：{valid}")
    return requested


def parse_args():
    parser = argparse.ArgumentParser(description="RTMP 推流诊断工具")
    parser.add_argument("--url", default=DEFAULT_RTMP_URL, help="RTMP 推流地址")
    parser.add_argument("--video", default=str(DEFAULT_VIDEO), help="测试视频路径")
    parser.add_argument("--duration", type=int, default=15, help="每档推流秒数")
    parser.add_argument("--probe-wait", type=int, default=3, help="推流结束后等待几秒再拉流")
    parser.add_argument("--probe-timeout", type=int, default=8, help="ffprobe 拉流超时秒数")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg 可执行文件路径")
    parser.add_argument("--ffprobe", default="ffprobe", help="ffprobe 可执行文件路径")
    parser.add_argument(
        "--profiles",
        type=parse_profile_names,
        default=[profile["name"] for profile in PROFILES],
        help="只测试指定档位，逗号分隔",
    )
    parser.add_argument("--no-probe", action="store_true", help="只推流，不做 ffprobe 拉流验证")
    return parser.parse_args()


def main():
    args = parse_args()
    video = Path(args.video).expanduser()
    if not video.is_absolute():
        video = (Path.cwd() / video).resolve()

    if not video.exists():
        print(f"测试视频不存在：{video}")
        return 2

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOG_DIR / f"rtmp_probe_{timestamp}.log"

    selected_profiles = [profile for profile in PROFILES if profile["name"] in args.profiles]

    write_log(log_file, "RTMP 推流诊断开始")
    write_log(log_file, f"工作目录：{ROOT_DIR}")
    write_log(log_file, f"测试视频：{video}")
    write_log(log_file, f"推流地址：{args.url}")
    write_log(log_file, f"日志文件：{log_file}")
    write_log(log_file, "")

    summaries = []
    for index, profile in enumerate(selected_profiles, start=1):
        write_log(log_file, "=" * 78)
        write_log(
            log_file,
            (
                f"[{index}/{len(selected_profiles)}] {profile['name']} "
                f"{profile['width']}x{profile['height']}@{profile['fps']}fps "
                f"{profile['bitrate']}"
            ),
        )

        ffmpeg_command = build_ffmpeg_command(video, args.url, profile, args.duration, args.ffmpeg)
        push_code, push_output = run_command(ffmpeg_command, log_file, timeout=args.duration + 30)

        probe_code = None
        probe_output = ""
        if not args.no_probe:
            write_log(log_file, f"等待 {args.probe_wait} 秒后开始拉流验证...")
            time.sleep(args.probe_wait)
            ffprobe_command = build_ffprobe_command(args.url, args.ffprobe, args.probe_timeout)
            probe_code, probe_output = run_command(ffprobe_command, log_file, timeout=args.probe_timeout + 5)

        conclusion = explain_result(push_code, probe_code, probe_output) if not args.no_probe else "已跳过拉流验证。"
        summaries.append((profile["name"], push_code, probe_code, conclusion))
        write_log(log_file, f"结论：{conclusion}")

        if "Connection refused" in push_output or "Cannot resolve" in push_output:
            write_log(log_file, "提示：日志里出现连接失败，优先检查网络、域名、端口和平台推流地址。")
        if "Broken pipe" in push_output:
            write_log(log_file, "提示：日志里出现 Broken pipe，通常是服务器主动断开或推流格式/权限不被接受。")

    write_log(log_file, "")
    write_log(log_file, "诊断汇总")
    for name, push_code, probe_code, conclusion in summaries:
        write_log(log_file, f"- {name}: push={push_code}, probe={probe_code}, {conclusion}")

    write_log(log_file, "")
    write_log(log_file, f"完成。完整日志：{log_file}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n用户中断")
        raise SystemExit(130)
    except FileNotFoundError as exc:
        missing = os.path.basename(str(exc.filename or ""))
        print(f"找不到命令：{missing}。请确认 ffmpeg/ffprobe 已加入 PATH，或用 --ffmpeg/--ffprobe 指定路径。")
        raise SystemExit(127)
