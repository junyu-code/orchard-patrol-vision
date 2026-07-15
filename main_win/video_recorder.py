"""桌面录像控件使用的轻量 OpenCV 视频写入器。"""

from pathlib import Path

import cv2
import numpy as np


class VideoRecorder:
    """将 BGR 帧按固定尺寸写入同一个本地视频文件。"""

    def __init__(self, writer_factory=None):
        self._writer_factory = writer_factory or cv2.VideoWriter
        self._writer = None
        self.path = None
        self.frame_size = None
        self.fps = None

    @property
    def active(self):
        return self._writer is not None

    def start(self, path, frame_size, fps):
        if self.active:
            raise RuntimeError("已有录像正在进行")

        width, height = (int(frame_size[0]), int(frame_size[1]))
        width = max(2, width - width % 2)
        height = max(2, height - height % 2)
        fps = float(fps)
        if not np.isfinite(fps) or fps <= 0:
            raise ValueError("录像帧率必须大于 0")

        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        codec = "MJPG" if output_path.suffix.lower() == ".avi" else "mp4v"
        writer = self._writer_factory(
            str(output_path),
            cv2.VideoWriter_fourcc(*codec),
            fps,
            (width, height),
        )
        if not writer.isOpened():
            writer.release()
            raise RuntimeError("无法创建录像文件，请检查 OpenCV 视频编码器")

        self._writer = writer
        self.path = output_path
        self.frame_size = (width, height)
        self.fps = fps

    def write(self, frame):
        if not self.active:
            raise RuntimeError("录像尚未开始")
        if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("录像帧必须是三通道 BGR 图像")

        width, height = self.frame_size
        if frame.shape[1] != width or frame.shape[0] != height:
            frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        self._writer.write(np.ascontiguousarray(frame))

    def stop(self):
        path = self.path
        if self._writer is not None:
            self._writer.release()
        self._writer = None
        self.path = None
        self.frame_size = None
        self.fps = None
        return path
