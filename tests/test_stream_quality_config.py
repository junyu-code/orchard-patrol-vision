import unittest

from config.app_config import build_config


class StreamQualityConfigTests(unittest.TestCase):
    def test_client_b_uses_source_stream_profile_by_default(self):
        config = build_config("client_b")

        self.assertEqual(config["RTMP_MAX_WIDTH"], 1280)
        self.assertEqual(config["RTMP_RESOLUTION"], "source")
        self.assertEqual(config["RTMP_MAX_FPS"], 0)
        self.assertEqual(config["RTMP_FRAME_RATE"], "source")
        self.assertEqual(config["RTMP_VIDEO_BITRATE"], "3000k")
        self.assertEqual(config["RTMP_MAXRATE"], "3600k")
        self.assertEqual(config["RTMP_BUFSIZE"], "6000k")
        self.assertEqual(config["RAW_FRAME_TARGET_FPS"], 0)
        self.assertEqual(config["PLAYBACK_RATE_FPS"], 0)
        self.assertEqual(config["CAMERA_RECONNECT_INTERVAL"], 1.0)
        self.assertEqual(config["RTMP_RECONNECT_INTERVAL"], 3.0)
        self.assertTrue(config["RTMP_TIMESTAMP_OVERLAY"])
        self.assertEqual(config["RTMP_TIME_STANDARD"], "utc+8")
        self.assertEqual(config["UDP_TIME_STANDARD"], "utc+8")
        self.assertEqual(config["UDP_HOST"], "1.14.205.24")
        self.assertEqual(config["SENSOR_ID"], 1)
        self.assertEqual(
            config["RTMP_URL"],
            "rtmp://gl.xsjny.com/live/vineyard1_robot1_sensor1",
        )
        self.assertEqual(
            config["RTMP_URL_LEFT"],
            "rtmp://gl.xsjny.com/live/vineyard1_robot1_sensor1",
        )
        self.assertEqual(
            config["RTMP_URL_RIGHT"],
            "rtmp://gl.xsjny.com/live/vineyard1_robot1_sensor2",
        )

if __name__ == "__main__":
    unittest.main()
