"""Camera resolution capability probing for the desktop controls."""

import re
import subprocess
import sys


_RESOLUTION_PATTERN = re.compile(r"(?<!\d)(\d{2,5})x(\d{2,5})(?!\d)")
_VIDEO_DEVICE_PATTERN = re.compile(r"^/dev/video(\d+)$")


def default_camera_source():
    """返回当前系统适用的默认相机名称。"""
    if sys.platform.startswith("linux"):
        return "/dev/video0"
    return "0"


def is_camera_source(source):
    """判断输入是否为摄像头编号或 Linux 视频设备路径。"""
    value = str(source or "").strip()
    return value.isnumeric() or bool(_VIDEO_DEVICE_PATTERN.match(value))


def camera_capture_source(source):
    """转换为 OpenCV 可接受的摄像头输入值。"""
    value = str(source or "").strip()
    match = _VIDEO_DEVICE_PATTERN.match(value)
    if match and not sys.platform.startswith("linux"):
        return int(match.group(1))
    return int(value) if value.isnumeric() else value


def camera_backend(cv2_module):
    """按操作系统选择较稳定的 OpenCV 摄像头后端。"""
    if sys.platform.startswith("linux"):
        return getattr(cv2_module, "CAP_V4L2", 0)
    if sys.platform.startswith("win"):
        return getattr(cv2_module, "CAP_DSHOW", 0)
    if sys.platform.startswith("darwin"):
        return getattr(cv2_module, "CAP_AVFOUNDATION", 0)
    return 0


def parse_supported_resolutions(output):
    """Return unique WxH modes ordered from smallest to largest area."""
    resolutions = {
        (int(width), int(height))
        for width, height in _RESOLUTION_PATTERN.findall(str(output or ""))
        if int(width) > 0 and int(height) > 0
    }
    return tuple(sorted(resolutions, key=lambda item: (item[0] * item[1], item)))


def camera_device_path(source):
    value = str(source or "").strip()
    if sys.platform.startswith("linux") and value.isnumeric():
        return f"/dev/video{value}"
    if sys.platform.startswith("linux") and _VIDEO_DEVICE_PATTERN.match(value):
        return value
    return None


def probe_camera_resolutions(source, timeout=3.0, runner=None):
    """Query V4L2 formats through FFmpeg without starting a video stream."""
    device = camera_device_path(source)
    if device is None:
        return ()
    runner = runner or subprocess.run
    command = [
        "ffmpeg",
        "-hide_banner",
        "-f",
        "v4l2",
        "-list_formats",
        "all",
        "-i",
        device,
    ]
    try:
        result = runner(
            command,
            capture_output=True,
            text=True,
            timeout=float(timeout),
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return ()
    return parse_supported_resolutions(
        f"{getattr(result, 'stdout', '')}\n{getattr(result, 'stderr', '')}"
    )


def probe_camera_max_resolution(source, timeout=3.0, runner=None):
    resolutions = probe_camera_resolutions(source, timeout=timeout, runner=runner)
    return resolutions[-1] if resolutions else None


def probe_camera_fps(source, capture_factory=None):
    value = str(source or "").strip()
    if not is_camera_source(value):
        return None
    try:
        import cv2

        camera_id = camera_capture_source(value)
        if capture_factory is not None:
            capture = capture_factory(camera_id)
        else:
            backend = camera_backend(cv2)
            capture = (
                cv2.VideoCapture(camera_id, backend)
                if backend
                else cv2.VideoCapture(camera_id)
            )
        try:
            if not capture.isOpened():
                return None
            fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
            return fps if fps > 0 else None
        finally:
            capture.release()
    except (ImportError, OSError, ValueError, RuntimeError):
        return None
