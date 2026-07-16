import unittest

import numpy as np

from transport.stream_resolution import (
    normalize_resolution_key,
    resize_frame_for_stream,
    resolve_stream_size,
)


class StreamResolutionTests(unittest.TestCase):
    def test_normalizes_common_profile_aliases(self):
        self.assertEqual(normalize_resolution_key("240p"), "426x240")
        self.assertEqual(normalize_resolution_key("720p"), "1280x720")
        self.assertEqual(normalize_resolution_key("1920 x 1080"), "1920x1080")
        self.assertEqual(normalize_resolution_key("2k"), "2560x1440")
        self.assertEqual(normalize_resolution_key("4k"), "3840x2160")
        self.assertEqual(normalize_resolution_key("auto"), "source")

    def test_additional_profiles_resolve_to_exact_encoder_sizes(self):
        self.assertEqual(
            resolve_stream_size(640, 480, resolution="540p"),
            (960, 540),
        )
        self.assertEqual(
            resolve_stream_size(1920, 1080, resolution="1440p"),
            (2560, 1440),
        )

    def test_explicit_profile_controls_encoder_size(self):
        self.assertEqual(
            resolve_stream_size(640, 480, resolution="1280x720"),
            (1280, 720),
        )

    def test_source_profile_keeps_even_source_dimensions(self):
        self.assertEqual(
            resolve_stream_size(641, 481, resolution="source"),
            (640, 480),
        )

    def test_legacy_max_width_still_preserves_source_ratio(self):
        self.assertEqual(
            resolve_stream_size(1920, 1080, legacy_max_width=1280),
            (1280, 720),
        )

    def test_resize_letterboxes_without_stretching_four_by_three_frame(self):
        frame = np.full((480, 640, 3), 255, dtype=np.uint8)

        output = resize_frame_for_stream(frame, 1280, 720)

        self.assertEqual(output.shape, (720, 1280, 3))
        self.assertEqual(np.count_nonzero(output[:, :160]), 0)
        self.assertEqual(np.count_nonzero(output[:, 1120:]), 0)
        self.assertGreater(np.count_nonzero(output[:, 160:1120]), 0)

    def test_resize_returns_original_frame_at_matching_size(self):
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        self.assertIs(resize_frame_for_stream(frame, 640, 360), frame)


if __name__ == "__main__":
    unittest.main()
