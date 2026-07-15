import unittest

from transport.serial_sender import SerialSender


class FakeSerial:
    def __init__(self, write_result=None, close_error=None):
        self.is_open = True
        self.write_result = write_result
        self.close_error = close_error
        self.writes = []
        self.flush_count = 0
        self.closed = False

    def write(self, data):
        self.writes.append(data)
        return len(data) if self.write_result is None else self.write_result

    def flush(self):
        self.flush_count += 1

    def close(self):
        self.closed = True
        if self.close_error:
            raise self.close_error


class SerialSenderTests(unittest.TestCase):
    def test_builds_expected_frame_and_clamps_confidence(self):
        self.assertEqual(SerialSender.build_frame(5, 0.85), bytes((0xFF, 5, 216, 0xFE)))
        self.assertEqual(SerialSender.build_frame(0, -1), bytes((0xFF, 0, 0, 0xFE)))
        self.assertEqual(SerialSender.build_frame(255, 2), bytes((0xFF, 255, 255, 0xFE)))

    def test_rejects_invalid_frame_fields(self):
        for disease_id in (-1, 256):
            with self.subTest(disease_id=disease_id):
                with self.assertRaises(ValueError):
                    SerialSender.build_frame(disease_id, 0.5)
        for confidence in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(confidence=confidence):
                with self.assertRaises(ValueError):
                    SerialSender.build_frame(1, confidence)

    def test_auto_detects_port_and_opens_with_8n1(self):
        fake = FakeSerial()
        calls = []

        def factory(**kwargs):
            calls.append(kwargs)
            return fake

        sender = SerialSender(
            port=None,
            serial_factory=factory,
            port_provider=lambda: [type("Port", (), {"device": "/dev/ttyTEST0"})()],
        )
        self.assertTrue(sender.open_serial())
        self.assertEqual(sender.port, "/dev/ttyTEST0")
        self.assertEqual(calls[0]["bytesize"], 8)
        self.assertEqual(calls[0]["parity"], "N")
        self.assertEqual(calls[0]["stopbits"], 1)
        self.assertFalse(calls[0]["rtscts"])

    def test_open_failure_does_not_leave_sender_open(self):
        sender = SerialSender(
            port="TEST",
            serial_factory=lambda **kwargs: (_ for _ in ()).throw(OSError("busy")),
        )
        self.assertFalse(sender.open_serial())
        self.assertFalse(sender.is_open)
        self.assertIsNone(sender.ser)

    def test_sends_complete_frame_and_flushes(self):
        fake = FakeSerial()
        sender = SerialSender(port="TEST", serial_factory=lambda **kwargs: fake)
        self.assertTrue(sender.open_serial())
        self.assertTrue(sender.pack_and_send(7, 1.0))
        self.assertEqual(fake.writes, [bytes((0xFF, 7, 255, 0xFE))])
        self.assertEqual(fake.flush_count, 1)

    def test_short_write_is_failure(self):
        fake = FakeSerial(write_result=2)
        sender = SerialSender(port="TEST", serial_factory=lambda **kwargs: fake)
        self.assertTrue(sender.open_serial())
        self.assertFalse(sender.pack_and_send(7, 0.5))

    def test_close_resets_state_even_when_driver_close_fails(self):
        fake = FakeSerial(close_error=OSError("disconnect"))
        sender = SerialSender(port="TEST", serial_factory=lambda **kwargs: fake)
        self.assertTrue(sender.open_serial())
        self.assertFalse(sender.close_serial(verbose=False))
        self.assertFalse(sender.is_open)
        self.assertIsNone(sender.ser)


if __name__ == "__main__":
    unittest.main()
