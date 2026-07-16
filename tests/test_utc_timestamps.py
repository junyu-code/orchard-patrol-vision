import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

import numpy as np

from transport.rtmp_sender import RtmpSender
from transport.udp_sender import UdpSender
from transport.video_timestamp import add_timestamp, format_timestamp


class UtcTimestampTests(unittest.TestCase):
    def test_formats_utc_time_as_beijing_iso_8601(self):
        utc_time = datetime(
            2026, 7, 16, 12, 30, 45, 123000,
            tzinfo=timezone.utc,
        )

        self.assertEqual(
            format_timestamp(utc_time, time_standard="utc+8"),
            "2026-07-16T20:30:45.123+08:00",
        )

    def test_video_overlay_returns_changed_copy(self):
        frame = np.zeros((120, 640, 3), dtype=np.uint8)

        rendered = add_timestamp(
            frame,
            datetime(2026, 7, 16, 12, 30, 45, tzinfo=timezone.utc),
            time_standard="utc+8",
        )

        self.assertFalse(np.shares_memory(frame, rendered))
        self.assertGreater(np.count_nonzero(rendered), 0)
        self.assertEqual(np.count_nonzero(frame), 0)

    def test_rtmp_sender_writes_overlay_without_mutating_source(self):
        sender = RtmpSender(overlay_timestamp=True, time_standard="utc+8")
        sender.process = Mock()
        sender.process.stdin = Mock()
        sender.is_running = True
        frame = np.zeros((120, 640, 3), dtype=np.uint8)

        self.assertTrue(sender.send_frame(frame))

        payload = sender.process.stdin.write.call_args.args[0]
        self.assertNotEqual(payload, frame.tobytes())
        self.assertEqual(np.count_nonzero(frame), 0)
        sender.process = None
        sender.is_running = False

    def test_udp_uses_beijing_time_without_changing_packet_size(self):
        utc_time = datetime(
            2026, 7, 16, 12, 30, 45,
            tzinfo=timezone.utc,
        )
        sender = UdpSender(
            udp_host="127.0.0.1",
            udp_port=9,
            time_standard="utc+8",
            clock=lambda: utc_time,
            sock=Mock(),
        )

        self.assertTrue(sender.send_robot_data(frame_index=7))

        packet = sender.sock.sendto.call_args.args[0]
        self.assertEqual(len(packet), 28)
        self.assertEqual(packet[9:12], bytes((20, 30, 45)))


if __name__ == "__main__":
    unittest.main()
