import unittest

from config.app_config import build_config
from transport.data_mode import (
    DATA_MODES,
    DEBUG_MODE,
    REAL_MODE,
    SIMULATION_MODE,
    empty_status_data,
    get_data_mode_policy,
    map_common_status_to_udp,
    merge_status_data,
    missing_udp_telemetry_fields,
    normalize_data_mode,
    select_gps_dms,
)
from transport.gps_protocol import GpsFix, GpsSnapshot


class DataModeTests(unittest.TestCase):
    def setUp(self):
        fix = GpsFix(
            "V1", "Robot_001", 1, 110.5, 25.25, 10.0, 2, 12, 0.5, 1000
        )
        self.valid_snapshot = GpsSnapshot(
            fix=fix,
            age_ms=0,
            stale=False,
            valid=True,
        )
        self.virtual_dms = (25, 1, 2.0, "N", 110, 3, 4.0, "E")

    def test_default_config_is_debug_mode(self):
        self.assertEqual(build_config("client_a")["DATA_MODE"], DEBUG_MODE)

    def test_all_modes_have_expected_sources(self):
        real = get_data_mode_policy(REAL_MODE)
        self.assertTrue(real.use_serial_gps)
        self.assertFalse(real.use_virtual_gps)
        self.assertFalse(real.use_virtual_status)
        self.assertFalse(real.use_virtual_events)

        debug = get_data_mode_policy(DEBUG_MODE)
        self.assertTrue(debug.use_serial_gps)
        self.assertTrue(debug.use_virtual_gps)
        self.assertTrue(debug.use_virtual_status)
        self.assertTrue(debug.use_virtual_events)
        self.assertFalse(debug.force_virtual)

        simulation = get_data_mode_policy(SIMULATION_MODE)
        self.assertFalse(simulation.use_serial_gps)
        self.assertTrue(simulation.use_virtual_gps)
        self.assertTrue(simulation.use_virtual_status)
        self.assertTrue(simulation.use_virtual_events)

    def test_rejects_unknown_mode(self):
        self.assertEqual(tuple(DATA_MODES), (REAL_MODE, DEBUG_MODE, SIMULATION_MODE))
        with self.assertRaises(ValueError):
            normalize_data_mode("mixed")

    def test_real_never_falls_back_to_virtual_gps(self):
        policy = get_data_mode_policy(REAL_MODE)
        self.assertIsNone(
            select_gps_dms(policy, GpsSnapshot.empty(), self.virtual_dms)
        )

    def test_debug_prefers_real_gps_then_falls_back_to_virtual(self):
        policy = get_data_mode_policy(DEBUG_MODE)
        self.assertEqual(
            select_gps_dms(policy, self.valid_snapshot, self.virtual_dms),
            (25, 15, 0.0, "N", 110, 30, 0.0, "E"),
        )
        self.assertEqual(
            select_gps_dms(policy, GpsSnapshot.empty(), self.virtual_dms),
            self.virtual_dms,
        )

    def test_simulation_ignores_real_snapshot(self):
        policy = get_data_mode_policy(SIMULATION_MODE)
        selected = select_gps_dms(
            policy,
            gps_snapshot=self.valid_snapshot,
            virtual_gps_dms=self.virtual_dms,
        )
        self.assertEqual(selected, self.virtual_dms)

    def test_real_missing_status_is_explicit_and_blocks_udp(self):
        status = empty_status_data()
        self.assertTrue(all(value is None for value in status.values()))
        missing = missing_udp_telemetry_fields(status, None)
        self.assertEqual(
            missing,
            [
                "robot_status",
                "velocity",
                "azimuth",
                "bat_voltage",
                "soc",
                "eyepoint_height",
                "gps",
            ],
        )

    def test_complete_debug_telemetry_can_be_encoded_for_udp(self):
        status = {
            "robot_status": 1,
            "velocity": 1.0,
            "azimuth": 90,
            "bat_voltage": 24.0,
            "soc": 80,
            "eyepoint_height": 1.5,
        }
        self.assertEqual(
            missing_udp_telemetry_fields(status, self.virtual_dms),
            [],
        )

    def test_debug_merges_each_status_field_with_real_priority(self):
        policy = get_data_mode_policy(DEBUG_MODE)
        merged = merge_status_data(
            policy,
            real_status_data={"velocity": 2.5, "soc": None},
            virtual_status_data={"velocity": 1.0, "soc": 80, "azimuth": 90},
        )
        self.assertEqual(merged["velocity"], 2.5)
        self.assertEqual(merged["soc"], 80)
        self.assertEqual(merged["azimuth"], 90)

    def test_simulation_ignores_real_status(self):
        policy = get_data_mode_policy(SIMULATION_MODE)
        merged = merge_status_data(
            policy,
            real_status_data={"velocity": 2.5},
            virtual_status_data={"velocity": 1.0},
        )
        self.assertEqual(merged["velocity"], 1.0)

    def test_common_robot_status_maps_to_legacy_udp_codes(self):
        self.assertEqual(map_common_status_to_udp(1), 0)
        self.assertEqual(map_common_status_to_udp(2), 1)
        self.assertEqual(map_common_status_to_udp(3), 2)
        self.assertEqual(map_common_status_to_udp(255), 255)
        self.assertEqual(map_common_status_to_udp(0, tree_present=True), 1)


if __name__ == "__main__":
    unittest.main()
