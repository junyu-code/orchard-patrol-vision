"""Timestamp rendering for frames sent to remote video streams."""

import cv2

from .time_standard import current_time, time_standard_label


def format_timestamp(value=None, time_standard="utc+8"):
    """Return an ISO-8601 timestamp with an explicit numeric offset."""
    clock = (lambda: value) if value is not None else None
    timestamp = current_time(time_standard, clock=clock)
    return timestamp.isoformat(timespec="milliseconds")


def add_timestamp(frame, value=None, time_standard="utc+8"):
    """Return a copy of ``frame`` with a readable timestamp overlay."""
    if frame is None or frame.ndim < 2:
        raise ValueError("frame must be a valid image")

    output = frame.copy()
    height, width = output.shape[:2]
    label = (
        f"{time_standard_label(time_standard)} "
        f"{format_timestamp(value, time_standard=time_standard)}"
    )
    font = cv2.FONT_HERSHEY_SIMPLEX
    padding = max(4, min(10, width // 100))
    available_width = max(1, width - 2 * padding)
    font_scale = min(0.7, max(0.32, width / 1280.0 * 0.7))

    text_size, _ = cv2.getTextSize(label, font, font_scale, 1)
    if text_size[0] > available_width:
        font_scale *= available_width / text_size[0]
    thickness = 2 if font_scale >= 0.6 else 1
    (text_width, text_height), baseline = cv2.getTextSize(
        label, font, font_scale, thickness
    )

    x = padding
    y = min(height - padding, padding + text_height)
    cv2.rectangle(
        output,
        (max(0, x - padding // 2), max(0, y - text_height - padding // 2)),
        (
            min(width - 1, x + text_width + padding // 2),
            min(height - 1, y + baseline + padding // 2),
        ),
        (0, 0, 0),
        -1,
    )
    cv2.putText(
        output,
        label,
        (x, y),
        font,
        font_scale,
        (255, 255, 255),
        thickness,
        cv2.LINE_AA,
    )
    return output
