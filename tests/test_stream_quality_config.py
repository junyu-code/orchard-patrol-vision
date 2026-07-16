import unittest

from config.app_config import build_config


class StreamQualityConfigTests(unittest.TestCase):
    def test_client_b_uses_hd_stream_profile(self):
        config = build_config("client_b")

        self.assertEqual(config["RTMP_MAX_WIDTH"], 1280)
        self.assertEqual(config["RTMP_RESOLUTION"], "1280x720")
        self.assertEqual(config["RTMP_MAX_FPS"], 30)
        self.assertEqual(config["RTMP_VIDEO_BITRATE"], "3000k")
        self.assertEqual(config["RTMP_MAXRATE"], "3600k")
        self.assertEqual(config["RTMP_BUFSIZE"], "6000k")
        self.assertEqual(config["RAW_FRAME_TARGET_FPS"], 30)
        self.assertEqual(config["PLAYBACK_RATE_FPS"], 30)
        self.assertTrue(config["RTMP_TIMESTAMP_OVERLAY"])
        self.assertEqual(config["RTMP_TIME_STANDARD"], "utc+8")
        self.assertEqual(config["UDP_TIME_STANDARD"], "utc+8")
        self.assertEqual(config["UDP_HOST"], "1.14.205.24")
        self.assertEqual(config["SENSOR_ID"], 2)
        self.assertEqual(
            config["RTMP_URL"],
            "rtmp://gl.xsjny.com/live/robot1_sensor2",
        )
        self.assertEqual(
            config["RTMP_URL_LEFT"],
            "rtmp://gl.xsjny.com/live/robot1_sensor1",
        )
        self.assertEqual(
            config["RTMP_URL_RIGHT"],
            "rtmp://gl.xsjny.com/live/robot1_sensor2",
        )

    def test_combined_preset_uses_same_hd_stream_profile(self):
        client_b = build_config("client_b")
        combined = build_config("both")

        stream_keys = (
            "RTMP_MAX_WIDTH",
            "RTMP_RESOLUTION",
            "RTMP_MAX_FPS",
            "RTMP_VIDEO_BITRATE",
            "RTMP_MAXRATE",
            "RTMP_BUFSIZE",
            "RAW_FRAME_TARGET_FPS",
            "PLAYBACK_RATE_FPS",
            "RTMP_TIMESTAMP_OVERLAY",
            "RTMP_TIME_STANDARD",
            "UDP_TIME_STANDARD",
        )
        self.assertEqual(
            {key: combined[key] for key in stream_keys},
            {key: client_b[key] for key in stream_keys},
        )


if __name__ == "__main__":
    unittest.main()
