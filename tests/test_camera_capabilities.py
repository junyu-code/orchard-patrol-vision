import unittest
from types import SimpleNamespace

from transport.camera_capabilities import (
    camera_device_path,
    parse_supported_resolutions,
    probe_camera_fps,
    probe_camera_max_resolution,
)


class CameraCapabilitiesTests(unittest.TestCase):
    def test_parses_unique_modes_and_orders_by_pixel_area(self):
        output = """
        YUYV 4:2:2 : 640x480 1920x1080 4656x3496 1920x1080
        Motion-JPEG : 4000x3000 1280x720
        """

        resolutions = parse_supported_resolutions(output)

        self.assertEqual(resolutions[0], (640, 480))
        self.assertEqual(resolutions[-1], (4656, 3496))
        self.assertEqual(resolutions.count((1920, 1080)), 1)

    def test_probe_returns_largest_reported_mode(self):
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return SimpleNamespace(
                stdout="",
                stderr="Motion-JPEG : 1280x720 3840x2160 4656x3496",
            )

        maximum = probe_camera_max_resolution("0", runner=runner)

        self.assertEqual(maximum, (4656, 3496))
        self.assertIn("/dev/video0", calls[0][0])
        self.assertEqual(calls[0][1]["timeout"], 3.0)

    def test_non_camera_source_is_not_probed(self):
        self.assertIsNone(camera_device_path("samples/video.mp4"))
        self.assertIsNone(probe_camera_max_resolution("samples/video.mp4"))

    def test_probes_camera_current_fps(self):
        class FakeCapture:
            def isOpened(self):
                return True

            def get(self, _property):
                return 15.0

            def release(self):
                self.released = True

        capture = FakeCapture()
        self.assertEqual(
            probe_camera_fps("0", capture_factory=lambda _source: capture),
            15.0,
        )
        self.assertTrue(capture.released)


if __name__ == "__main__":
    unittest.main()
