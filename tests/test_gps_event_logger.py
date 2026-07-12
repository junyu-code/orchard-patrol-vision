from datetime import date, datetime
import json
from pathlib import Path
import tempfile
import unittest

from transport.gps_event_logger import GpsEventLogger
from transport.gps_protocol import GpsFix, GpsSnapshot


class GpsEventLoggerTests(unittest.TestCase):
    def test_writes_utf8_jsonl_and_keeps_three_days(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir)
            clock_value = int(datetime(2026, 7, 12, 12, 0, 0).timestamp() * 1000)
            logger = GpsEventLogger(
                log_dir=str(log_dir),
                retention_days=3,
                clock_ms=lambda: clock_value,
            )

            for name in [
                "2026-07-08.jsonl",
                "2026-07-09.jsonl",
                "2026-07-10.jsonl",
                "2026-07-11.jsonl",
                "notes.jsonl",
            ]:
                (log_dir / name).write_text("old\n", encoding="utf-8")
            logger.cleanup_old_files(reference_date=date(2026, 7, 12))

            self.assertFalse((log_dir / "2026-07-08.jsonl").exists())
            self.assertFalse((log_dir / "2026-07-09.jsonl").exists())
            self.assertTrue((log_dir / "2026-07-10.jsonl").exists())
            self.assertTrue((log_dir / "2026-07-11.jsonl").exists())
            self.assertTrue((log_dir / "notes.jsonl").exists())

            fix = GpsFix("V1", "Robot_001", 7, 110.2, 25.1, 140.0, 2, 12, 0.5, clock_value)
            snapshot = GpsSnapshot(fix=fix, age_ms=20, stale=False, valid=True)
            path = logger.log_event(
                event_type="disease",
                channel="http",
                frame_index=99,
                source_time_s=1.5,
                gps_snapshot=snapshot,
                diseases={"溃疡病": {"count": 1, "confidence": 0.9}},
            )

            record = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
            self.assertEqual(record["frame_index"], 99)
            self.assertEqual(record["diseases"]["溃疡病"]["count"], 1)
            self.assertEqual(record["gps"]["sequence"], 7)
            self.assertTrue(record["gps"]["valid"])


if __name__ == "__main__":
    unittest.main()
