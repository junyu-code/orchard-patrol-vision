import unittest

from transport.stream_framerate import (
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

    def test_explicit_profile_controls_encoder_rate(self):
        self.assertEqual(resolve_stream_fps(15, frame_rate="10", max_fps=30), 10)
        self.assertEqual(resolve_stream_fps(15, frame_rate="30", max_fps=30), 30)

    def test_rejects_unsupported_profile(self):
        with self.assertRaises(ValueError):
            normalize_frame_rate_key("120 FPS")


if __name__ == "__main__":
    unittest.main()
