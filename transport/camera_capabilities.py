"""Camera resolution capability probing for the desktop controls."""

import re
import subprocess
import sys


_RESOLUTION_PATTERN = re.compile(r"(?<!\d)(\d{2,5})x(\d{2,5})(?!\d)")


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
    if value.startswith("/dev/video"):
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
    if not value.isnumeric():
        return None
    try:
        import cv2

        camera_id = int(value)
        if capture_factory is not None:
            capture = capture_factory(camera_id)
        elif sys.platform.startswith("linux"):
            capture = cv2.VideoCapture(camera_id, cv2.CAP_V4L2)
        elif sys.platform.startswith("win"):
            capture = cv2.VideoCapture(camera_id, cv2.CAP_DSHOW)
        else:
            capture = cv2.VideoCapture(camera_id)
        try:
            if not capture.isOpened():
                return None
            fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
            return fps if fps > 0 else None
        finally:
            capture.release()
    except (ImportError, OSError, ValueError, RuntimeError):
        return None
