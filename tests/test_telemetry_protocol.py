import unittest

from transport.telemetry_protocol import (
    DEFINED_FLAGS_MASK,
    FLAG_GPS,
    FLAG_ROUTE,
    FLAG_TREE,
    FLAG_VELOCITY,
    TelemetryChecksumError,
    TelemetryProtocolError,
    TelemetryStreamBuffer,
    build_telemetry_packet,
    unpack_telemetry_packet,
)


STANDARD_PACKET_HEX = (
    "AA 55 01 01 00 01 00 2E 01 01 03 FF 00 01 00 0A "
    "00 01 00 01 00 02 01 04 0C 00 34 41 BD C4 D5 0E F0 "
    "12 21 00 00 36 E0 66 94 60 40 23 28 04 B0 05 DC 5D "
    "C0 55 00 00 7A 17 0D 0A"
)
STANDARD_PACKET = bytes.fromhex(STANDARD_PACKET_HEX)


def build_standard_packet(**overrides):
    values = {
        "sequence": 1,
        "robot_id": 1,
        "robot_status": 1,
        "valid_flags": DEFINED_FLAGS_MASK,
        "route_id": 1,
        "waypoint_id": 10,
        "current_tree_id": 1,
        "left_tree_id": 1,
        "right_tree_id": 2,
        "camera_side": 1,
        "gps_fix": 4,
        "satellites": 12,
        "hdop_x100": 52,
        "longitude_e7": 1_102_955_733,
        "latitude_e7": 250_614_305,
        "altitude_cm": 14_048,
        "timestamp": 1_721_000_000,
        "azimuth_x100": 9_000,
        "velocity_mm_s": 1_200,
        "camera_height_mm": 1_500,
        "battery_mv": 24_000,
        "soc": 85,
        "fault_code": 0,
    }
    values.update(overrides)
    return build_telemetry_packet(**values)


class TelemetryProtocolTests(unittest.TestCase):
    def test_builds_documented_standard_packet(self):
        self.assertEqual(build_standard_packet(), STANDARD_PACKET)

    def test_unpacks_physical_values_and_tree_ids(self):
        telemetry = unpack_telemetry_packet(STANDARD_PACKET, received_at_ms=123456)

        self.assertEqual(telemetry.sequence, 1)
        self.assertEqual(telemetry.left_tree_id, 1)
        self.assertEqual(telemetry.right_tree_id, 2)
        self.assertAlmostEqual(telemetry.longitude, 110.2955733)
        self.assertAlmostEqual(telemetry.latitude, 25.0614305)
        self.assertAlmostEqual(telemetry.actual_velocity_mps, 1.2)
        self.assertEqual(telemetry.to_status_data()["bat_voltage"], 24.0)
        self.assertEqual(telemetry.to_tree_data()["tree_code"], "ID0001")
        self.assertEqual(telemetry.received_at_ms, 123456)

    def test_rejects_crc_error(self):
        damaged = bytearray(STANDARD_PACKET)
        damaged[30] ^= 0x01
        with self.assertRaises(TelemetryChecksumError):
            unpack_telemetry_packet(bytes(damaged))

    def test_stream_buffer_handles_noise_split_and_sticky_packets(self):
        stream = TelemetryStreamBuffer()
        packet = STANDARD_PACKET

        self.assertEqual(stream.feed(b"noise" + packet[:17]), [])
        packets = stream.feed(packet[17:] + packet, received_at_ms=5000)

        self.assertEqual(len(packets), 2)
        self.assertEqual(packets[0].sequence, 1)
        self.assertEqual(packets[1].sequence, 1)
        self.assertGreaterEqual(stream.stats["discarded_bytes"], 5)

    def test_missing_velocity_can_use_estimated_speed(self):
        flags = DEFINED_FLAGS_MASK & ~FLAG_VELOCITY
        packet = build_standard_packet(valid_flags=flags, velocity_mm_s=0)
        telemetry = unpack_telemetry_packet(packet)

        self.assertIsNone(telemetry.actual_velocity_mps)
        self.assertEqual(telemetry.to_status_data(estimated_speed_mps=0.75)["velocity"], 0.75)

    def test_invalid_fields_must_be_zero(self):
        flags = FLAG_GPS | FLAG_ROUTE | FLAG_TREE
        with self.assertRaises(TelemetryProtocolError):
            build_standard_packet(valid_flags=flags, velocity_mm_s=1200)

    def test_current_tree_must_match_camera_side(self):
        with self.assertRaises(TelemetryProtocolError):
            build_standard_packet(current_tree_id=2, camera_side=1)


if __name__ == "__main__":
    unittest.main()
