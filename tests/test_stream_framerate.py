import unittest

from transport.stream_framerate import (
    StreamFramePacer,
    frame_rate_label,
    normalize_frame_rate_key,
    resolve_stream_fps,
)


class StreamFrameRateTests(unittest.TestCase):
    def test_normalizes_source_and_numeric_profiles(self):
        self.assertEqual(normalize_frame_rate_key("auto"), "source")
        self.assertEqual(normalize_frame_rate_key("15 FPS"), "15")
        self.assertEqual(frame_rate_label("24"), "24 FPS")

    def test_source_profile_follows_camera_with_configured_cap(self):
        self.assertEqual(
            resolve_stream_fps(60, frame_rate="source", max_fps=30),
            30,
        )
        self.assertEqual(
            resolve_stream_fps(15, frame_rate="source", max_fps=30),
            15,
        )
        self.assertEqual(
            resolve_stream_fps(29.97, frame_rate="source", max_fps=0),
            29.97,
        )

    def test_explicit_profile_controls_encoder_rate(self):
        self.assertEqual(resolve_stream_fps(15, frame_rate="10", max_fps=30), 10)
        # 源帧率不足时不伪造更高的编码帧率，避免视频时间轴加速。
        self.assertEqual(resolve_stream_fps(15, frame_rate="30", max_fps=30), 15)

    def test_rejects_unsupported_profile(self):
        with self.assertRaises(ValueError):
            normalize_frame_rate_key("120 FPS")

    def test_pacer_sleeps_until_next_output_deadline(self):
        now = [0.0]
        sleeps = []

        def clock():
            return now[0]

        def sleeper(delay):
            sleeps.append(delay)
            now[0] += delay

        pacer = StreamFramePacer(10, clock=clock, sleeper=sleeper)
        pacer.wait()
        pacer.wait()
        pacer.wait()

        self.assertEqual(len(sleeps), 2)
        self.assertAlmostEqual(sleeps[0], 0.1, places=6)
        self.assertAlmostEqual(sleeps[1], 0.1, places=6)

    def test_pacer_subtracts_frame_processing_time(self):
        now = [0.0]
        sleeps = []

        def sleeper(delay):
            sleeps.append(delay)
            now[0] += delay

        pacer = StreamFramePacer(
            10,
            clock=lambda: now[0],
            sleeper=sleeper,
        )
        pacer.wait()
        now[0] += 0.03
        pacer.wait()

        self.assertEqual(len(sleeps), 1)
        self.assertAlmostEqual(sleeps[0], 0.07, places=6)


if __name__ == "__main__":
    unittest.main()
