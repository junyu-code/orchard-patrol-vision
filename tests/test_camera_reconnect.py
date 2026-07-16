import unittest

import numpy as np

from main import LoadRawFrames


class FakeCapture:
    def __init__(self, frames, opened=True):
        self.frames = list(frames)
        self.opened = opened
        self.released = False

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
        return 30


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


def cv2_flip(frame):
    return frame[:, ::-1]


if __name__ == "__main__":
    unittest.main()
