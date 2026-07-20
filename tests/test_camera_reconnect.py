import unittest

import cv2
import numpy as np

from main import LoadRawFrames


class FakeCapture:
    def __init__(self, frames, opened=True, fps=30):
        self.frames = list(frames)
        self.opened = opened
        self.released = False
        self.fps = fps

    def isOpened(self):
        return self.opened and not self.released

    def read(self):
        if not self.frames:
            return False, None
        return self.frames.pop(0)

    def release(self):
        self.released = True

    def set(self, *_args):
        return True

    def get(self, _property):
        return self.fps


class IndexedCapture:
    def __init__(self, frame_count=12, fps=30):
        self.frames = [
            np.full((2, 2, 3), index, dtype=np.uint8)
            for index in range(frame_count)
        ]
        self.fps = fps
        self.position = 0
        self.released = False

    def isOpened(self):
        return not self.released

    def read(self):
        if self.position >= len(self.frames):
            return False, None
        frame = self.frames[self.position]
        self.position += 1
        return True, frame

    def release(self):
        self.released = True

    def set(self, property_id, value):
        if property_id == cv2.CAP_PROP_POS_FRAMES:
            self.position = int(value)
        return True

    def get(self, property_id):
        if property_id == cv2.CAP_PROP_FPS:
            return self.fps
        if property_id == cv2.CAP_PROP_FRAME_COUNT:
            return len(self.frames)
        if property_id == cv2.CAP_PROP_POS_FRAMES:
            return self.position
        return 0


class CameraReconnectTests(unittest.TestCase):
    def test_camera_read_failure_reopens_device_and_returns_new_frame(self):
        first_capture = FakeCapture([(False, None)])
        recovered_frame = np.zeros((4, 6, 3), dtype=np.uint8)
        second_capture = FakeCapture([(True, recovered_frame)])
        captures = [first_capture, second_capture]

        loader = LoadRawFrames(
            "0",
            camera_reconnect_interval=0,
            capture_factory=lambda _source: captures.pop(0),
        )

        path, _, frame, active_capture = next(loader)

        self.assertTrue(first_capture.released)
        self.assertIs(active_capture, second_capture)
        self.assertEqual(path, "webcam.jpg")
        np.testing.assert_array_equal(frame, cv2_flip(recovered_frame))

    def test_camera_reconnect_can_be_interrupted_during_shutdown(self):
        capture = FakeCapture([(False, None)])
        loader = LoadRawFrames(
            "0",
            camera_reconnect_interval=0,
            should_stop=lambda: True,
            capture_factory=lambda _source: capture,
        )

        with self.assertRaises(StopIteration):
            next(loader)

        self.assertTrue(capture.released)

    def test_file_source_drops_frames_to_match_target_fps(self):
        capture = IndexedCapture(frame_count=12, fps=30)
        loader = LoadRawFrames(
            "video.mp4",
            target_fps=10,
            capture_factory=lambda _source: capture,
        )

        values = [int(next(loader)[2][0, 0, 0]) for _ in range(4)]

        self.assertEqual(values, [0, 3, 6, 9])

    def test_camera_source_handles_fractional_drop_ratio(self):
        capture = IndexedCapture(frame_count=10, fps=30)
        loader = LoadRawFrames(
            "0",
            target_fps=20,
            capture_factory=lambda _source: capture,
        )

        values = [int(next(loader)[2][0, 0, 0]) for _ in range(4)]

        self.assertEqual(values, [0, 2, 3, 5])


def cv2_flip(frame):
    return frame[:, ::-1]


if __name__ == "__main__":
    unittest.main()
