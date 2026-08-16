"""Runtime controls for the systemd-supervised desktop application.

The UI can use a distinct exit status for an intentional close.  Repeated
intentional closes are treated as a request to pause the supervised service,
without weakening automatic recovery for actual crashes.
"""

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path


# These values are configured in deploy/yolo-detect.service.
RESTART_AFTER_UI_CLOSE_EXIT_CODE = 75
PAUSE_SUPERVISED_SERVICE_EXIT_CODE = 77
DEFAULT_UI_CLOSE_LIMIT = 3
DEFAULT_UI_CLOSE_WINDOW_SECONDS = 60


@dataclass(frozen=True)
class SupervisedCloseDecision:
    """The service action selected after a supervised UI close."""

    close_count: int
    close_limit: int
    should_pause: bool
    exit_code: int


def register_supervised_ui_close(
    state_path,
    close_limit=DEFAULT_UI_CLOSE_LIMIT,
    window_seconds=DEFAULT_UI_CLOSE_WINDOW_SECONDS,
    now=None,
):
    """Record one UI close and choose whether the service should restart.

    State is cleared once the close limit is reached, so a later manual
    ``systemctl --user start`` begins a new sequence.
    """
    state_path = Path(state_path)
    close_limit = _positive_int(close_limit, DEFAULT_UI_CLOSE_LIMIT)
    window_seconds = _positive_int(
        window_seconds,
        DEFAULT_UI_CLOSE_WINDOW_SECONDS,
    )
    now = time.time() if now is None else float(now)

    previous = _read_state(state_path)
    elapsed = None if previous is None else now - previous["last_close_at"]
    if previous and 0 <= elapsed <= window_seconds:
        close_count = previous["close_count"] + 1
    else:
        close_count = 1

    should_pause = close_count >= close_limit
    if should_pause:
        _remove_state(state_path)
        return SupervisedCloseDecision(
            close_count=close_count,
            close_limit=close_limit,
            should_pause=True,
            exit_code=PAUSE_SUPERVISED_SERVICE_EXIT_CODE,
        )

    _write_state(
        state_path,
        {
            "version": 1,
            "last_close_at": now,
            "close_count": close_count,
        },
    )
    return SupervisedCloseDecision(
        close_count=close_count,
        close_limit=close_limit,
        should_pause=False,
        exit_code=RESTART_AFTER_UI_CLOSE_EXIT_CODE,
    )


def _positive_int(value, default):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _read_state(state_path):
    try:
        with state_path.open("r", encoding="utf-8") as state_file:
            data = json.load(state_file)
        close_count = int(data["close_count"])
        last_close_at = float(data["last_close_at"])
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
        return None

    if close_count < 1:
        return None
    return {"close_count": close_count, "last_close_at": last_close_at}


def _write_state(state_path, data):
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = state_path.with_name(
        ".{}.{}.tmp".format(state_path.name, os.getpid())
    )
    try:
        with temporary_path.open("w", encoding="utf-8") as state_file:
            json.dump(data, state_file, ensure_ascii=True)
            state_file.write("\n")
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, state_path)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def _remove_state(state_path):
    try:
        state_path.unlink()
    except FileNotFoundError:
        pass
