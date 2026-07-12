"""带保留期限的 GPS 事件 JSONL 日志。"""

from datetime import date, datetime, timedelta
import json
from pathlib import Path
import re
import threading
import time
from typing import Callable, Optional

from .gps_protocol import GpsSnapshot


DAILY_LOG_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})\.jsonl$")


class GpsEventLogger:
    """按天追加事件，并只保留配置天数内的日志。"""

    def __init__(
        self,
        log_dir: str,
        retention_days: int = 3,
        clock_ms: Optional[Callable[[], int]] = None,
    ):
        self.log_dir = Path(log_dir)
        self.retention_days = max(1, int(retention_days))
        self.clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)
        self._lock = threading.Lock()
        self._current_date = None
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.cleanup_old_files()

    def log_event(
        self,
        event_type: str,
        channel: str,
        frame_index: int,
        source_time_s: Optional[float],
        gps_snapshot: GpsSnapshot,
        diseases: Optional[dict] = None,
        tree_event: Optional[dict] = None,
    ) -> Path:
        """追加一条带 GPS 快照的业务事件。"""
        logged_at_ms = int(self.clock_ms())
        log_date = datetime.fromtimestamp(logged_at_ms / 1000.0).date()
        record = {
            "logged_at_ms": logged_at_ms,
            "event_type": str(event_type),
            "channel": str(channel),
            "frame_index": int(frame_index),
            "source_time_s": None if source_time_s is None else float(source_time_s),
            "diseases": diseases,
            "tree_event": tree_event,
            "gps": gps_snapshot.to_dict(),
        }

        with self._lock:
            if log_date != self._current_date:
                self.cleanup_old_files(reference_date=log_date, lock_held=True)
                self._current_date = log_date
            path = self.log_dir / f"{log_date.isoformat()}.jsonl"
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
                handle.write("\n")
        return path

    def cleanup_old_files(
        self,
        reference_date: Optional[date] = None,
        lock_held: bool = False,
    ):
        """删除保留窗口之前、且符合日期命名规则的日志。"""
        if not lock_held:
            with self._lock:
                return self.cleanup_old_files(reference_date=reference_date, lock_held=True)

        current_date = reference_date or datetime.now().date()
        oldest_kept_date = current_date - timedelta(days=self.retention_days - 1)
        if not self.log_dir.exists():
            return

        for path in self.log_dir.iterdir():
            if not path.is_file():
                continue
            match = DAILY_LOG_PATTERN.fullmatch(path.name)
            if not match:
                continue
            try:
                file_date = date.fromisoformat(match.group(1))
            except ValueError:
                continue
            if file_date < oldest_kept_date:
                path.unlink()
