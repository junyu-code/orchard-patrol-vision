"""Common RTMP output resolutions and aspect-preserving frame resizing."""

import cv2
import numpy as np


COMMON_STREAM_RESOLUTIONS = (
    ("source", "跟随源画面", None, None),
    ("640x360", "360p  640 x 360", 640, 360),
    ("854x480", "480p  854 x 480", 854, 480),
    ("1280x720", "720p  1280 x 720", 1280, 720),
    ("1920x1080", "1080p  1920 x 1080", 1920, 1080),
)

_RESOLUTION_BY_KEY = {
    key: (width, height)
    for key, _label, width, height in COMMON_STREAM_RESOLUTIONS
}
_RESOLUTION_ALIASES = {
    "360p": "640x360",
    "480p": "854x480",
    "720p": "1280x720",
    "1080p": "1920x1080",
    "auto": "source",
    "original": "source",
}


def normalize_resolution_key(value):
    key = str(value or "source").strip().lower().replace(" ", "")
    key = key.replace("*", "x").replace("×", "x")
    key = _RESOLUTION_ALIASES.get(key, key)
    if key not in _RESOLUTION_BY_KEY:
        valid = ", ".join(_RESOLUTION_BY_KEY)
        raise ValueError(f"unsupported stream resolution: {value!r}; valid: {valid}")
    return key


def resolution_label(value):
    key = normalize_resolution_key(value)
    for option_key, label, _width, _height in COMMON_STREAM_RESOLUTIONS:
        if option_key == key:
            return label
    return key


def resolve_stream_size(
    source_width,
    source_height,
    resolution=None,
    legacy_max_width=0,
):
    """Resolve an even encoder size, retaining the old max-width fallback."""
    source_width = int(source_width)
    source_height = int(source_height)
    if source_width <= 0 or source_height <= 0:
        raise ValueError("source dimensions must be positive")

    if resolution:
        key = normalize_resolution_key(resolution)
        width, height = _RESOLUTION_BY_KEY[key]
        if width is not None and height is not None:
            return int(width), int(height)
    else:
        max_width = max(0, int(legacy_max_width or 0))
        if max_width and source_width > max_width:
            scale = max_width / source_width
            source_width = max_width
            source_height = round(source_height * scale)

    width = max(2, source_width - source_width % 2)
    height = max(2, source_height - source_height % 2)
    return width, height


def resize_frame_for_stream(frame, output_width, output_height):
    """Fit a frame inside the output canvas without stretching or cropping."""
    if frame is None or frame.ndim < 2:
        raise ValueError("frame must be a valid image")

    output_width = int(output_width)
    output_height = int(output_height)
    if output_width <= 0 or output_height <= 0:
        raise ValueError("output dimensions must be positive")

    source_height, source_width = frame.shape[:2]
    if source_width == output_width and source_height == output_height:
        return frame

    scale = min(output_width / source_width, output_height / source_height)
    resized_width = max(1, min(output_width, round(source_width * scale)))
    resized_height = max(1, min(output_height, round(source_height * scale)))
    interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
    resized = cv2.resize(
        frame,
        (resized_width, resized_height),
        interpolation=interpolation,
    )

    canvas_shape = (output_height, output_width) + tuple(frame.shape[2:])
    canvas = np.zeros(canvas_shape, dtype=frame.dtype)
    x = (output_width - resized_width) // 2
    y = (output_height - resized_height) // 2
    canvas[y:y + resized_height, x:x + resized_width] = resized
    return np.ascontiguousarray(canvas)
