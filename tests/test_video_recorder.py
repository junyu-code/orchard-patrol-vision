import tempfile
import unittest
from pathlib import Path

import numpy as np

from main_win.video_recorder import VideoRecorder


class FakeWriter:
    def __init__(self, opened=True):
        self.opened = opened
        self.frames = []
        self.released = False

    def isOpened(self):
        return self.opened

    def write(self, frame):
        self.frames.append(frame.copy())

    def release(self):
        self.released = True


class VideoRecorderTests(unittest.TestCase):
    def test_start_normalizes_odd_dimensions_and_write_resizes_frames(self):
        calls = []
        fake_writer = FakeWriter()

        def writer_factory(path, codec, fps, frame_size):
            calls.append((path, codec, fps, frame_size))
            return fake_writer

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "recordings" / "camera.mp4"
            recorder = VideoRecorder(writer_factory=writer_factory)
            recorder.start(output, (641, 479), 25)
            recorder.write(np.zeros((120, 160, 3), dtype=np.uint8))
            stopped_path = recorder.stop()

        self.assertEqual(calls[0][2:], (25.0, (640, 478)))
        self.assertEqual(fake_writer.frames[0].shape, (478, 640, 3))
        self.assertTrue(fake_writer.released)
        self.assertEqual(stopped_path, output)
        self.assertFalse(recorder.active)

    def test_start_reports_unavailable_encoder(self):
        fake_writer = FakeWriter(opened=False)
        recorder = VideoRecorder(writer_factory=lambda *args: fake_writer)

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "无法创建录像文件"):
                recorder.start(Path(directory) / "ui.mp4", (1280, 720), 15)

        self.assertTrue(fake_writer.released)
        self.assertFalse(recorder.active)

    def test_write_requires_bgr_frame(self):
        fake_writer = FakeWriter()
        recorder = VideoRecorder(writer_factory=lambda *args: fake_writer)

        with tempfile.TemporaryDirectory() as directory:
            recorder.start(Path(directory) / "ui.mp4", (320, 240), 15)
            with self.assertRaisesRegex(ValueError, "三通道 BGR"):
                recorder.write(np.zeros((240, 320), dtype=np.uint8))
            recorder.stop()


if __name__ == "__main__":
    unittest.main()
