import unittest

from config.app_config import PRESET_NAMES, build_config


class PlatformPresetTests(unittest.TestCase):
    def test_all_supported_presets_are_buildable(self):
        self.assertEqual(PRESET_NAMES, ("client_a", "client_b", "both"))
        for preset_name in PRESET_NAMES:
            config = build_config(preset_name)
            self.assertEqual(config["PRESET_NAME"], preset_name)

    def test_client_a_selects_http_without_udp(self):
        config = build_config("client_a")

        self.assertTrue(config["ENABLE_HTTP"])
        self.assertFalse(config["ENABLE_UDP"])
        self.assertTrue(config["ENABLE_RTMP"])
        self.assertFalse(config["ENABLE_PATROL_TIMELINE"])
        self.assertEqual(
            config["HTTP_URL"],
            "https://api.jdpm.hhzzss.cn/agriculture/position/robotPost",
        )

    def test_client_b_selects_udp_without_http(self):
        config = build_config("client_b")

        self.assertFalse(config["ENABLE_HTTP"])
        self.assertTrue(config["ENABLE_UDP"])
        self.assertTrue(config["ENABLE_RTMP"])
        self.assertTrue(config["ENABLE_PATROL_TIMELINE"])
        self.assertEqual(config["UDP_HOST"], "1.14.205.24")
        self.assertEqual(config["UDP_PORT"], 4926)

    def test_both_enables_both_protocol_adapters(self):
        config = build_config("both")

        self.assertTrue(config["ENABLE_HTTP"])
        self.assertTrue(config["ENABLE_UDP"])
        self.assertTrue(config["ENABLE_RTMP"])


if __name__ == "__main__":
    unittest.main()
