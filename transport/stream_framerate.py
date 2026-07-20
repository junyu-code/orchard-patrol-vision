"""RTMP 输出帧率配置、归一化与节流。"""

import time


COMMON_STREAM_FRAME_RATES = (
    ("source", "跟随源帧率", None),
    ("5", "5 FPS", 5),
    ("10", "10 FPS", 10),
    ("15", "15 FPS", 15),
    ("20", "20 FPS", 20),
    ("24", "24 FPS", 24),
    ("25", "25 FPS", 25),
    ("30", "30 FPS", 30),
)

_FRAME_RATE_BY_KEY = {
    key: fps
    for key, _label, fps in COMMON_STREAM_FRAME_RATES
}


def normalize_frame_rate_key(value):
    key = str(value if value is not None else "source").strip().lower()
    key = key.replace("fps", "").strip()
    if key in {"auto", "original", "follow", "source"}:
        return "source"
    if key not in _FRAME_RATE_BY_KEY:
        valid = ", ".join(_FRAME_RATE_BY_KEY)
        raise ValueError(f"unsupported stream frame rate: {value!r}; valid: {valid}")
    return key


def frame_rate_label(value):
    key = normalize_frame_rate_key(value)
    for option_key, label, _fps in COMMON_STREAM_FRAME_RATES:
        if option_key == key:
            return label
    return key


def resolve_stream_fps(source_fps, frame_rate=None, max_fps=0):
    source_fps = float(source_fps or 0)
    if source_fps <= 0:
        source_fps = 25.0

    key = normalize_frame_rate_key(frame_rate)
    configured_fps = _FRAME_RATE_BY_KEY[key]
    resolved_fps = source_fps if configured_fps is None else float(configured_fps)

    # 没有补帧器时不能把低帧率源伪装成更高帧率，否则视频时间轴会加速。
    resolved_fps = min(resolved_fps, source_fps)

    max_fps = float(max_fps or 0)
    if max_fps > 0:
        resolved_fps = min(resolved_fps, max_fps)
    return max(1.0, round(resolved_fps, 3))


class StreamFramePacer:
    """按输出帧率节流文件读取，避免 FFmpeg 收帧过快。"""

    def __init__(self, fps, clock=None, sleeper=None):
        self.fps = max(1.0, float(fps or 0))
        self.interval = 1.0 / self.fps
        self.clock = clock or time.monotonic
        self.sleeper = sleeper or time.sleep
        self.next_deadline = None

    def reset(self):
        self.next_deadline = None

    def wait(self):
        now = self.clock()
        if self.next_deadline is None:
            self.next_deadline = now
        delay = self.next_deadline - now
        if delay > 0:
            self.sleeper(delay)
            now = self.clock()
        # 处理推理或编码偶发卡顿，避免后续连续补发造成突发流量。
        if now - self.next_deadline > self.interval * 4:
            self.next_deadline = now
        self.next_deadline += self.interval
