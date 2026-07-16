import unittest
from unittest.mock import patch

import numpy as np

from transport.rtmp_sender import RtmpSender


class FakeStdin:
    def __init__(self):
        self.frames = []
        self.closed = False

    def write(self, data):
        self.frames.append(data)

    def close(self):
        self.closed = True


class FakeProcess:
    def __init__(self, return_code=None):
        self.return_code = return_code
        self.stdin = FakeStdin()

    def poll(self):
        return self.return_code

    def wait(self, timeout=None):
        self.return_code = 0
        return self.return_code

    def kill(self):
        self.return_code = -9


class RtmpSenderTests(unittest.TestCase):
    @patch("transport.rtmp_sender.subprocess.Popen")
    def test_start_reports_success_and_reuses_live_process(self, popen):
        process = FakeProcess()
        popen.return_value = process
        sender = RtmpSender("rtmp://example.test/live")

        self.assertTrue(sender.start(640, 360, 15))
        self.assertTrue(sender.start(640, 360, 15))
        self.assertEqual(popen.call_count, 1)
        sender.stop()

    def test_send_frame_marks_exited_process_as_stopped(self):
        sender = RtmpSender("rtmp://example.test/live")
        sender.process = FakeProcess(return_code=1)
        sender.is_running = True

        self.assertFalse(sender.send_frame(np.zeros((2, 2, 3), dtype=np.uint8)))
        self.assertFalse(sender.is_running)
        self.assertIsNone(sender.process)


if __name__ == "__main__":
    unittest.main()
