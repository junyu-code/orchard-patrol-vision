"""RTMP output frame-rate profiles and normalization."""


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

    max_fps = float(max_fps or 0)
    if max_fps > 0:
        resolved_fps = min(resolved_fps, max_fps)
    return max(1, int(round(resolved_fps)))
