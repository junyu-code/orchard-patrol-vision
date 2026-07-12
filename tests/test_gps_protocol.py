import unittest

from transport.gps_protocol import (
    GpsChecksumError,
    GpsFix,
    GpsLineBuffer,
    GpsProtocolError,
    GpsSnapshot,
    calculate_checksum,
    parse_gps_sentence,
    select_frame_gps_dms,
)


VALID_LINE = (
    "$OPGPS,V1,Robot_001,200,110.29557332,25.06143046,"
    "140.48,2,12,0.52*0C\r\n"
)


def build_line(body):
    return f"${body}*{calculate_checksum(body):02X}\r\n"


class GpsProtocolTests(unittest.TestCase):
    def test_parse_valid_example(self):
        fix = parse_gps_sentence(VALID_LINE, received_at_ms=123456)

        self.assertEqual(fix.robot_id, "Robot_001")
        self.assertEqual(fix.sequence, 200)
        self.assertAlmostEqual(fix.longitude, 110.29557332)
        self.assertAlmostEqual(fix.latitude, 25.06143046)
        self.assertEqual(fix.fix_quality, 2)
        self.assertTrue(fix.position_valid)
        self.assertEqual(fix.received_at_ms, 123456)

    def test_rejects_bad_checksum(self):
        with self.assertRaises(GpsChecksumError):
            parse_gps_sentence(VALID_LINE.replace("*0C", "*00"))

    def test_rejects_bad_version_and_field_count(self):
        with self.assertRaises(GpsProtocolError):
            parse_gps_sentence(build_line("OPGPS,V2,Robot_001,1,110,25,1,2,12,0.5"))
        with self.assertRaises(GpsProtocolError):
            parse_gps_sentence(build_line("OPGPS,V1,Robot_001,1,110,25"))

    def test_rejects_non_ascii_and_out_of_range_values(self):
        with self.assertRaises(GpsProtocolError):
            parse_gps_sentence(b"\xff\xfe\n")
        with self.assertRaises(GpsProtocolError):
            parse_gps_sentence(build_line("OPGPS,V1,R1,1,181,25,1,2,12,0.5"))
        with self.assertRaises(GpsProtocolError):
            parse_gps_sentence(build_line("OPGPS,V1,R1,1,110,91,1,2,12,0.5"))
        with self.assertRaises(GpsProtocolError):
            parse_gps_sentence(build_line("OPGPS,V1,R1,1,110,25,1,3,12,0.5"))
        with self.assertRaises(GpsProtocolError):
            parse_gps_sentence(build_line("OPGPS,V1,R1,1,110,25,nan,2,12,0.5"))

    def test_invalid_fix_is_parsed_but_position_is_invalid(self):
        fix = parse_gps_sentence(
            build_line("OPGPS,V1,R1,1,110.1,25.1,1.0,0,0,99.99"),
            received_at_ms=1000,
        )
        self.assertFalse(fix.position_valid)

    def test_stream_buffer_handles_split_and_sticky_packets(self):
        buffer = GpsLineBuffer()
        encoded = VALID_LINE.encode("ascii")

        self.assertEqual(buffer.feed(encoded[:10]), [])
        self.assertEqual(buffer.feed(encoded[10:-1]), [])
        lines = buffer.feed(encoded[-1:] + encoded)

        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], encoded.rstrip(b"\r\n"))
        self.assertEqual(lines[1], encoded.rstrip(b"\r\n"))

    def test_stream_buffer_recovers_after_overflow(self):
        buffer = GpsLineBuffer(max_buffer_bytes=128)
        buffer.feed(b"x" * 200)
        self.assertEqual(buffer.overflow_count, 1)

        lines = buffer.feed(VALID_LINE.encode("ascii"))
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0], VALID_LINE.encode("ascii").rstrip(b"\r\n"))

    def test_frame_selection_never_falls_back_when_gps_is_enabled(self):
        fallback = (25, 1, 2.0, "N", 110, 3, 4.0, "E")
        self.assertEqual(select_frame_gps_dms(False, None, fallback), fallback)
        self.assertEqual(
            select_frame_gps_dms(True, GpsSnapshot.empty(), fallback),
            (0, 0, 0.0, "N", 0, 0, 0.0, "E"),
        )

        fix = GpsFix("V1", "R1", 1, 110.5, 25.25, 10.0, 2, 12, 0.5, 1000)
        snapshot = GpsSnapshot(fix=fix, age_ms=0, stale=False, valid=True)
        selected = select_frame_gps_dms(True, snapshot, fallback)
        self.assertEqual(selected[:4], (25, 15, 0.0, "N"))
        self.assertEqual(selected[4:], (110, 30, 0.0, "E"))


if __name__ == "__main__":
    unittest.main()
