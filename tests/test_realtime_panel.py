import unittest

from main_win.realtime_panel import (
    EMPTY_VALUE,
    build_realtime_view,
    format_battery,
    format_gps_dms,
    format_tree_event,
)


class RealtimePanelTests(unittest.TestCase):
    def test_real_serial_source_keeps_unavailable_status_as_dash(self):
        view = build_realtime_view({
            "data_mode": "debug",
            "work_mode": "YOLO识别",
            "frame_index": 0,
            "disease_count": 0,
            "status": {
                "velocity": None,
                "azimuth": None,
                "soc": None,
                "bat_voltage": None,
            },
            "gps_dms": (25, 3, 4.2, "N", 110, 17, 44.1, "E"),
            "gps": {"source": "serial", "valid": True, "simulated": False},
            "field_sources": {
                "velocity": "unavailable",
                "azimuth": "unavailable",
                "battery": "unavailable",
                "frame_index": "real",
                "disease_count": "real",
            },
        })

        self.assertEqual(view["data_source"], "real")
        self.assertEqual(view["data_source_label"], "真实数据")
        self.assertEqual(view["field_sources"]["gps"], "real")
        self.assertEqual(view["field_sources"]["frame_index"], "real")
        self.assertEqual(view["values"]["velocity"], EMPTY_VALUE)
        self.assertEqual(view["values"]["azimuth"], EMPTY_VALUE)
        self.assertEqual(view["values"]["battery"], EMPTY_VALUE)
        self.assertEqual(view["values"]["frame_index"], "0")
        self.assertEqual(view["values"]["disease_count"], "0 个")
        self.assertTrue(view["gps_available"])

    def test_virtual_fallback_is_clearly_marked(self):
        view = build_realtime_view({
            "data_mode": "debug",
            "gps_dms": (25, 3, 4.2, "N", 110, 17, 44.1, "E"),
            "gps": {"source": "virtual", "valid": True, "simulated": True},
            "field_sources": {"gps": "virtual"},
        })

        self.assertEqual(view["data_source"], "virtual")
        self.assertEqual(view["data_source_label"], "虚拟数据")
        self.assertEqual(view["field_sources"]["gps"], "virtual")

    def test_invalid_serial_data_keeps_waiting_for_real_fix(self):
        view = build_realtime_view({
            "data_mode": "real",
            "gps_dms": None,
            "gps": {"source": "serial", "valid": False, "simulated": False},
        })

        self.assertEqual(view["data_source"], "waiting")
        self.assertEqual(view["data_source_label"], "等待真实数据")
        self.assertEqual(view["field_sources"]["gps"], "unavailable")

    def test_each_available_field_keeps_its_declared_source(self):
        view = build_realtime_view({
            "status": {
                "velocity": 1.2,
                "azimuth": 90,
                "soc": 80,
                "bat_voltage": 24,
            },
            "field_sources": {
                "velocity": "virtual",
                "azimuth": "real",
                "battery": "virtual",
            },
        })

        self.assertEqual(view["field_sources"]["velocity"], "virtual")
        self.assertEqual(view["field_sources"]["azimuth"], "real")
        self.assertEqual(view["field_sources"]["battery"], "virtual")
        self.assertEqual(view["field_sources"]["gps"], "unavailable")

    def test_gps_estimated_speed_keeps_yellow_source_state(self):
        view = build_realtime_view({
            "status": {"velocity": 0.86},
            "field_sources": {"velocity": "estimated"},
        })

        self.assertEqual(view["values"]["velocity"], "0.86 m/s")
        self.assertEqual(view["field_sources"]["velocity"], "estimated")

    def test_zero_telemetry_is_displayed_as_real_data(self):
        view = build_realtime_view({
            "status": {
                "velocity": 0,
                "azimuth": 0,
                "soc": 0,
                "bat_voltage": 0,
            },
        })

        self.assertEqual(view["values"]["velocity"], "0.00 m/s")
        self.assertEqual(view["values"]["azimuth"], "0°")
        self.assertEqual(view["values"]["battery"], "0%  ·  0.0 V")

    def test_battery_only_includes_available_measurements(self):
        self.assertEqual(format_battery(80, None), "80%")
        self.assertEqual(format_battery(None, 24), "24.0 V")
        self.assertEqual(format_battery(None, None), EMPTY_VALUE)
        self.assertEqual(format_battery("invalid", 24), "24.0 V")

    def test_invalid_gps_does_not_leak_partial_values(self):
        self.assertEqual(format_gps_dms(None), EMPTY_VALUE)
        self.assertEqual(
            format_gps_dms((25, 3, None, "N", 110, 17, 44.1, "E")),
            EMPTY_VALUE,
        )

    def test_real_status_without_gps_still_marks_source_as_real(self):
        view = build_realtime_view({
            "status": {"robot_status": 1},
            "field_sources": {"robot_status": "real"},
        })

        self.assertEqual(view["data_source"], "real")
        self.assertEqual(view["data_source_label"], "真实数据")

    def test_debug_real_and_virtual_fields_are_marked_mixed(self):
        view = build_realtime_view({
            "status": {"robot_status": 1, "velocity": 0.5},
            "field_sources": {
                "robot_status": "real",
                "velocity": "virtual",
            },
        })

        self.assertEqual(view["data_source"], "mixed")
        self.assertEqual(view["data_source_label"], "真实/虚拟混合")

    def test_tree_ids_are_padded_and_zero_state_is_explicit(self):
        self.assertEqual(
            format_tree_event({
                "current_tree_id": 1,
                "left_tree_id": 1,
                "right_tree_id": 2,
            }),
            "当前 0001\n左 0001 · 右 0002",
        )
        self.assertEqual(
            format_tree_event({
                "current_tree_id": 0,
                "left_tree_id": 0,
                "right_tree_id": 0,
            }),
            "当前无树",
        )


if __name__ == "__main__":
    unittest.main()
