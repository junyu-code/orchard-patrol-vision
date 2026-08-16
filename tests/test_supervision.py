import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication, QMainWindow

from main import MainWindow, schedule_application_exit
from transport.supervision import (
    PAUSE_SUPERVISED_SERVICE_EXIT_CODE,
    RESTART_AFTER_UI_CLOSE_EXIT_CODE,
    register_supervised_ui_close,
)


class SupervisedCloseTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temporary_directory.name) / "ui-close.json"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_third_close_within_window_pauses_service(self):
        first = register_supervised_ui_close(
            self.state_path,
            close_limit=3,
            window_seconds=60,
            now=100,
        )
        second = register_supervised_ui_close(
            self.state_path,
            close_limit=3,
            window_seconds=60,
            now=120,
        )
        third = register_supervised_ui_close(
            self.state_path,
            close_limit=3,
            window_seconds=60,
            now=140,
        )

        self.assertEqual(first.close_count, 1)
        self.assertFalse(first.should_pause)
        self.assertEqual(first.exit_code, RESTART_AFTER_UI_CLOSE_EXIT_CODE)
        self.assertEqual(second.close_count, 2)
        self.assertFalse(second.should_pause)
        self.assertTrue(third.should_pause)
        self.assertEqual(third.close_count, 3)
        self.assertEqual(third.exit_code, PAUSE_SUPERVISED_SERVICE_EXIT_CODE)
        self.assertFalse(self.state_path.exists())

    def test_close_after_window_starts_a_new_sequence(self):
        register_supervised_ui_close(
            self.state_path,
            close_limit=3,
            window_seconds=60,
            now=100,
        )
        decision = register_supervised_ui_close(
            self.state_path,
            close_limit=3,
            window_seconds=60,
            now=161,
        )

        self.assertEqual(decision.close_count, 1)
        self.assertFalse(decision.should_pause)

    def test_clock_rollback_starts_a_new_sequence(self):
        register_supervised_ui_close(
            self.state_path,
            close_limit=3,
            window_seconds=60,
            now=100,
        )
        decision = register_supervised_ui_close(
            self.state_path,
            close_limit=3,
            window_seconds=60,
            now=99,
        )

        self.assertEqual(decision.close_count, 1)
        self.assertFalse(decision.should_pause)

    def test_invalid_state_is_replaced_with_a_new_sequence(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text("not json", encoding="utf-8")

        decision = register_supervised_ui_close(self.state_path, now=100)

        self.assertEqual(decision.close_count, 1)
        self.assertEqual(decision.exit_code, RESTART_AFTER_UI_CLOSE_EXIT_CODE)
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(state["close_count"], 1)

    def test_supervised_window_close_uses_pause_exit_code_on_third_close(self):
        environment = {
            "ORCHARD_SUPERVISED": "1",
            "ORCHARD_UI_CLOSE_STATE_FILE": str(self.state_path),
            "ORCHARD_UI_CLOSE_LIMIT": "3",
            "ORCHARD_UI_CLOSE_WINDOW_SECONDS": "60",
        }

        with patch.dict(os.environ, environment, clear=False):
            self.assertEqual(
                MainWindow._ui_close_exit_code(),
                RESTART_AFTER_UI_CLOSE_EXIT_CODE,
            )
            self.assertEqual(
                MainWindow._ui_close_exit_code(),
                RESTART_AFTER_UI_CLOSE_EXIT_CODE,
            )
            self.assertEqual(
                MainWindow._ui_close_exit_code(),
                PAUSE_SUPERVISED_SERVICE_EXIT_CODE,
            )

    def test_qt_event_loop_preserves_pause_exit_code(self):
        app = QApplication.instance() or QApplication([])

        class TestWindow(QMainWindow):
            def closeEvent(self, event):
                schedule_application_exit(
                    app,
                    PAUSE_SUPERVISED_SERVICE_EXIT_CODE,
                )
                event.accept()

        window = TestWindow()
        window.show()
        fallback_timer = QTimer()
        fallback_timer.setSingleShot(True)
        fallback_timer.timeout.connect(lambda: app.exit(99))
        QTimer.singleShot(0, window.close)
        fallback_timer.start(1000)

        exit_code = app.exec_()
        fallback_timer.stop()

        self.assertEqual(exit_code, PAUSE_SUPERVISED_SERVICE_EXIT_CODE)

    def test_systemd_service_restarts_every_exit_except_pause_code(self):
        service_text = Path(__file__).parents[1].joinpath(
            "deploy", "yolo-detect.service"
        ).read_text(encoding="utf-8")

        self.assertIn("Restart=always", service_text)
        self.assertIn("SuccessExitStatus=77", service_text)
        self.assertIn("RestartPreventExitStatus=77", service_text)


if __name__ == "__main__":
    unittest.main()
