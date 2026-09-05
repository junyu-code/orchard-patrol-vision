import unittest

from transport.hid_pos_receiver import (
    DualHidPosReceiver,
    HidTagReading,
    HidTagSideSnapshot,
    HidTagSnapshot,
    decode_em22_hid_pos_report,
    merge_hid_tag_tree_data,
    parse_tree_tag,
    select_tree_id_data,
)


class HidPosReceiverTests(unittest.TestCase):
    def test_new_scan_replaces_previous_tree_id_immediately(self):
        now = [1000]
        receiver = DualHidPosReceiver(
            left_serial="AB031246",
            right_serial="AB030000",
            hid_backend=object(),
            clock_ms=lambda: now[0],
        )

        self.assertTrue(receiver._handle_barcode_data("left", b"214"))
        now[0] = 1001
        self.assertTrue(receiver._handle_barcode_data("left", b"315"))

        snapshot = receiver.get_snapshot()
        self.assertEqual(snapshot.left.tree_id, 315)
        self.assertEqual(snapshot.left.reading.raw_text, "315")

    def test_scan_expires_at_thirty_minutes_without_new_data(self):
        receiver = DualHidPosReceiver(
            left_serial="AB031246",
            right_serial="AB030000",
            hid_backend=object(),
            clock_ms=lambda: 1000,
        )
        self.assertTrue(receiver._handle_barcode_data("left", b"214"))

        snapshot = receiver.get_snapshot(now_ms=1000 + 30 * 60 * 1000)
        self.assertTrue(snapshot.left.stale)
        self.assertFalse(snapshot.left.valid)
        self.assertIsNone(snapshot.left.tree_id)

    def test_decodes_em22_report_with_report_id_and_length(self):
        report = bytes([2, 3]) + b"214" + bytes(59)
        self.assertEqual(decode_em22_hid_pos_report(report), b"214")

    def test_decodes_report_without_report_id(self):
        self.assertEqual(
            decode_em22_hid_pos_report(bytes([3]) + b"214" + bytes(53)),
            b"214",
        )

    def test_rejects_truncated_report(self):
        with self.assertRaises(ValueError):
            decode_em22_hid_pos_report(bytes([2, 4]) + b"214")

    def test_parses_numeric_tag(self):
        receiver = DualHidPosReceiver(
            left_serial="AB031246",
            right_serial="AB030000",
            hid_backend=object(),
        )
        self.assertEqual(parse_tree_tag("214", receiver.tag_pattern), 214)
        self.assertEqual(parse_tree_tag("TREE:00214", receiver.tag_pattern), 214)

    def test_merges_scanned_sides_and_keeps_telemetry_fields(self):
        left = HidTagReading("left", 214, "214", "AB031246", 1000)
        right = HidTagReading("right", 315, "315", "AB030000", 900)
        snapshot = HidTagSnapshot(
            left=HidTagSideSnapshot(left, 0, False, True),
            right=HidTagSideSnapshot(right, 100, False, True),
        )
        merged = merge_hid_tag_tree_data(
            {
                "current_tree_id": 1,
                "left_tree_id": 10,
                "right_tree_id": 11,
                "route_index": 4,
            },
            snapshot,
        )
        self.assertEqual(merged["left_tree_id"], 214)
        self.assertEqual(merged["right_tree_id"], 315)
        self.assertEqual(merged["current_tree_id"], 214)
        self.assertEqual(merged["camera_side"], 1)
        self.assertEqual(merged["route_index"], 4)
        self.assertEqual(merged["source"], "mixed_hid_pos")

    def test_stale_tags_do_not_create_tree_data(self):
        snapshot = HidTagSnapshot(
            left=HidTagSideSnapshot(None, None, True, False),
            right=HidTagSideSnapshot(None, None, True, False),
        )
        self.assertIsNone(merge_hid_tag_tree_data(None, snapshot))

    def test_stale_tags_clear_previous_tree_ids_in_base_data(self):
        reading = HidTagReading("left", 214, "214", "AB031246", 1000)
        snapshot = HidTagSnapshot(
            left=HidTagSideSnapshot(reading, 30 * 60 * 1000, True, False),
            right=HidTagSideSnapshot.empty(),
        )

        result = merge_hid_tag_tree_data(
            {
                "current_tree_id": 214,
                "left_tree_id": 214,
                "right_tree_id": 315,
                "tree_code": "ID0214",
            },
            snapshot,
        )

        self.assertEqual(result["current_tree_id"], 0)
        self.assertEqual(result["left_tree_id"], 0)
        self.assertEqual(result["right_tree_id"], 0)
        self.assertEqual(result["camera_side"], 0)
        self.assertEqual(result["tree_code"], "")

    def test_hid_mode_falls_back_to_telemetry_tree_ids_when_tag_is_missing(self):
        empty = HidTagSnapshot.empty()
        result = merge_hid_tag_tree_data(
            {"current_tree_id": 9, "left_tree_id": 9, "right_tree_id": 10},
            empty,
            hid_only=False,
        )
        self.assertEqual(result["current_tree_id"], 9)
        self.assertEqual(result["left_tree_id"], 9)
        self.assertEqual(result["right_tree_id"], 10)

    def test_hid_mode_overrides_only_scanned_side(self):
        left = HidTagReading("left", 214, "214", "AB031246", 1000)
        snapshot = HidTagSnapshot(
            left=HidTagSideSnapshot(left, 0, False, True),
            right=HidTagSideSnapshot.empty(),
        )
        result = merge_hid_tag_tree_data(
            {"current_tree_id": 9, "left_tree_id": 9, "right_tree_id": 10},
            snapshot,
            hid_only=False,
        )
        self.assertEqual(result["current_tree_id"], 214)
        self.assertEqual(result["left_tree_id"], 214)
        self.assertEqual(result["right_tree_id"], 10)
        self.assertEqual(result["source"], "mixed_hid_pos")

    def test_tree_source_switch_off_ignores_scanned_ids(self):
        telemetry = {
            "current_tree_id": 9,
            "left_tree_id": 9,
            "right_tree_id": 10,
        }
        left = HidTagReading("left", 214, "214", "AB031246", 1000)
        snapshot = HidTagSnapshot(
            left=HidTagSideSnapshot(left, 0, False, True),
            right=HidTagSideSnapshot.empty(),
        )

        result = select_tree_id_data(telemetry, snapshot, use_hid_tags=False)

        self.assertEqual(result, telemetry)

    def test_tree_source_switch_on_falls_back_to_telemetry_ids(self):
        telemetry = {
            "current_tree_id": 9,
            "left_tree_id": 9,
            "right_tree_id": 10,
        }

        result = select_tree_id_data(
            telemetry,
            HidTagSnapshot.empty(),
            use_hid_tags=True,
        )

        self.assertEqual(result["current_tree_id"], 9)
        self.assertEqual(result["left_tree_id"], 9)
        self.assertEqual(result["right_tree_id"], 10)

    def test_serial_numbers_must_be_distinct(self):
        with self.assertRaises(ValueError):
            DualHidPosReceiver("same", "same", hid_backend=object())


if __name__ == "__main__":
    unittest.main()
