import unittest

from transport.telemetry_protocol import (
    FLAG_GPS,
    FLAG_VELOCITY,
    build_telemetry_packet,
    unpack_telemetry_packet,
)
from transport.telemetry_serial_receiver import TelemetrySerialReceiver


def telemetry_at(
    sequence,
    received_at_ms,
    longitude_e7=1_102_955_733,
    velocity_mm_s=None,
):
    flags = FLAG_GPS
    velocity_value = 0
    if velocity_mm_s is not None:
        flags |= FLAG_VELOCITY
        velocity_value = velocity_mm_s
    packet = build_telemetry_packet(
        sequence=sequence,
        robot_id=1,
        robot_status=1,
        valid_flags=flags,
        gps_fix=4,
        satellites=12,
        hdop_x100=52,
        longitude_e7=longitude_e7,
        latitude_e7=250_614_305,
        altitude_cm=14_048,
        velocity_mm_s=velocity_value,
    )
    return unpack_telemetry_packet(packet, received_at_ms=received_at_ms)


class TelemetrySerialReceiverTests(unittest.TestCase):
    def build_receiver(self, **overrides):
        values = {
            "port": "COM_TEST",
            "auto_detect": False,
            "serial_factory": lambda **kwargs: None,
            "clock_ms": lambda: 2000,
            "speed_min_interval": 1.0,
            "speed_max_interval": 5.0,
            "speed_min_distance": 0.0,
            "speed_max_mps": 8.0,
            "speed_smoothing_alpha": 0.35,
        }
        values.update(overrides)
        return TelemetrySerialReceiver(**values)

    def test_actual_serial_velocity_has_priority(self):
        receiver = self.build_receiver()
        receiver._handle_telemetry(telemetry_at(1, 1000, velocity_mm_s=1500))

        snapshot = receiver.get_snapshot(now_ms=1000)

        self.assertTrue(snapshot.valid)
        self.assertEqual(snapshot.to_status_data()["velocity"], 1.5)
        self.assertIsNone(snapshot.estimated_speed_mps)

    def test_estimates_speed_only_when_serial_velocity_is_missing(self):
        receiver = self.build_receiver()
        receiver._handle_telemetry(telemetry_at(1, 1000))
        receiver._handle_telemetry(
            telemetry_at(2, 2000, longitude_e7=1_102_955_833)
        )

        snapshot = receiver.get_snapshot(now_ms=2000)

        self.assertIsNone(snapshot.telemetry.actual_velocity_mps)
        self.assertIsNotNone(snapshot.estimated_speed_mps)
        self.assertAlmostEqual(
            snapshot.to_status_data()["velocity"],
            snapshot.estimated_speed_mps,
        )
        self.assertGreater(snapshot.estimated_speed_mps, 0.5)
        self.assertLess(snapshot.estimated_speed_mps, 2.0)

    def test_rejects_unreasonable_gps_speed(self):
        receiver = self.build_receiver(speed_max_mps=2.0)
        receiver._handle_telemetry(telemetry_at(1, 1000))
        receiver._handle_telemetry(
            telemetry_at(2, 2000, longitude_e7=1_103_955_733)
        )

        snapshot = receiver.get_snapshot(now_ms=2000)

        self.assertIsNone(snapshot.estimated_speed_mps)
        self.assertEqual(receiver.get_stats()["speed_rejections"], 1)

    def test_duplicate_packet_does_not_replace_latest_snapshot(self):
        receiver = self.build_receiver()
        first = telemetry_at(7, 1000)
        duplicate = telemetry_at(7, 2000, longitude_e7=1_102_955_833)
        receiver._handle_telemetry(first)
        receiver._handle_telemetry(duplicate)

        snapshot = receiver.get_snapshot(now_ms=2000)

        self.assertEqual(snapshot.telemetry.received_at_ms, 1000)
        self.assertEqual(receiver.get_stats()["duplicate_packets"], 1)
        self.assertEqual(receiver.get_stats()["valid_packets"], 1)

    def test_snapshot_becomes_stale(self):
        receiver = self.build_receiver(stale_timeout=1.0)
        receiver._handle_telemetry(telemetry_at(1, 1000))

        snapshot = receiver.get_snapshot(now_ms=2001)

        self.assertTrue(snapshot.stale)
        self.assertFalse(snapshot.valid)
        self.assertEqual(snapshot.to_status_data(), {})


if __name__ == "__main__":
    unittest.main()
