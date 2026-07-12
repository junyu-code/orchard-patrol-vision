import threading
import time
import unittest

from transport.gps_protocol import calculate_checksum
from transport.gps_serial_receiver import GpsSerialReceiver


def build_line(sequence=1, fix_quality=2):
    body = (
        f"OPGPS,V1,Robot_001,{sequence},110.29557332,25.06143046,"
        f"140.48,{fix_quality},12,0.52"
    )
    return f"${body}*{calculate_checksum(body):02X}\r\n".encode("ascii")


class FakeSerial:
    def __init__(self, chunks, fail_after=False):
        self._chunks = list(chunks)
        self._lock = threading.Lock()
        self._closed = False
        self._fail_after = fail_after

    @property
    def in_waiting(self):
        with self._lock:
            return len(self._chunks[0]) if self._chunks else 0

    def read(self, size):
        with self._lock:
            if self._closed:
                return b""
            if self._chunks:
                chunk = self._chunks.pop(0)
                if len(chunk) > size:
                    self._chunks.insert(0, chunk[size:])
                    chunk = chunk[:size]
                return chunk
            if self._fail_after:
                self._fail_after = False
                raise OSError("模拟串口断开")
        time.sleep(0.005)
        return b""

    def close(self):
        with self._lock:
            self._closed = True


def wait_until(predicate, timeout=1.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class GpsSerialReceiverTests(unittest.TestCase):
    def test_invalid_packet_does_not_replace_latest_fix(self):
        now = [1000]
        valid = build_line(sequence=1)
        invalid = build_line(sequence=2)
        invalid = invalid[:-4] + b"00\r\n"
        fake = FakeSerial([valid[:20], valid[20:] + invalid])
        receiver = GpsSerialReceiver(
            port="TEST",
            auto_detect=False,
            serial_factory=lambda **kwargs: fake,
            clock_ms=lambda: now[0],
            reconnect_interval=0.02,
        )

        receiver.start()
        self.assertTrue(wait_until(lambda: receiver.get_stats()["valid_packets"] == 1))
        receiver.stop()

        snapshot = receiver.get_snapshot(now_ms=1000)
        self.assertEqual(snapshot.fix.sequence, 1)
        self.assertEqual(receiver.get_stats()["checksum_errors"], 1)

    def test_stale_boundary_and_invalid_fix(self):
        now = [1000]
        fake = FakeSerial([build_line(sequence=3)])
        receiver = GpsSerialReceiver(
            port="TEST",
            auto_detect=False,
            stale_timeout=1.0,
            serial_factory=lambda **kwargs: fake,
            clock_ms=lambda: now[0],
        )
        receiver.start()
        self.assertTrue(wait_until(lambda: receiver.get_stats()["valid_packets"] == 1))

        self.assertTrue(receiver.get_snapshot(now_ms=2000).valid)
        stale = receiver.get_snapshot(now_ms=2001)
        self.assertTrue(stale.stale)
        self.assertFalse(stale.valid)
        receiver.stop()

        invalid_fake = FakeSerial([build_line(sequence=4, fix_quality=0)])
        invalid_receiver = GpsSerialReceiver(
            port="TEST",
            auto_detect=False,
            serial_factory=lambda **kwargs: invalid_fake,
            clock_ms=lambda: 3000,
        )
        invalid_receiver.start()
        self.assertTrue(wait_until(lambda: invalid_receiver.get_stats()["valid_packets"] == 1))
        self.assertFalse(invalid_receiver.get_snapshot(now_ms=3000).valid)
        invalid_receiver.stop()

    def test_open_failure_then_reconnects(self):
        calls = []
        fake = FakeSerial([build_line(sequence=9)])

        def factory(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise OSError("首次打开失败")
            return fake

        receiver = GpsSerialReceiver(
            port="TEST",
            auto_detect=False,
            serial_factory=factory,
            reconnect_interval=0.02,
        )
        receiver.start()
        self.assertTrue(wait_until(lambda: receiver.get_stats()["valid_packets"] == 1))
        receiver.stop()

        self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(receiver.get_stats()["connect_failures"], 1)
        self.assertEqual(calls[1]["baudrate"], 9600)

    def test_read_failure_then_reconnects(self):
        connections = [
            FakeSerial([], fail_after=True),
            FakeSerial([build_line(sequence=10)]),
        ]

        def factory(**kwargs):
            return connections.pop(0)

        receiver = GpsSerialReceiver(
            port="TEST",
            auto_detect=False,
            serial_factory=factory,
            reconnect_interval=0.02,
        )
        receiver.start()
        self.assertTrue(wait_until(lambda: receiver.get_stats()["valid_packets"] == 1))
        receiver.stop()

        self.assertEqual(receiver.get_stats()["read_failures"], 1)
        self.assertGreaterEqual(receiver.get_stats()["reconnects"], 1)

    def test_auto_detect_skips_non_gps_port_and_selects_valid_port(self):
        opened_ports = []

        def factory(**kwargs):
            port = kwargs["port"]
            opened_ports.append(port)
            if port == "/dev/ttyUSB0":
                return FakeSerial([b"DEBUG OUTPUT\r\n"])
            return FakeSerial([build_line(sequence=20)])

        receiver = GpsSerialReceiver(
            port="",
            auto_detect=True,
            probe_timeout=0.03,
            reconnect_interval=0.02,
            serial_factory=factory,
            port_provider=lambda: ["/dev/ttyUSB0", "/dev/ttyACM0"],
        )
        receiver.start()
        self.assertTrue(wait_until(lambda: receiver.active_port == "/dev/ttyACM0"))
        self.assertEqual(receiver.get_snapshot().fix.sequence, 20)
        receiver.stop()

        self.assertEqual(opened_ports[:2], ["/dev/ttyUSB0", "/dev/ttyACM0"])
        self.assertEqual(receiver.get_stats()["probe_failures"], 1)

    def test_auto_detect_excludes_other_business_serial_port(self):
        opened_ports = []

        def factory(**kwargs):
            opened_ports.append(kwargs["port"])
            return FakeSerial([build_line(sequence=21)])

        receiver = GpsSerialReceiver(
            auto_detect=True,
            probe_timeout=0.03,
            excluded_ports=["/dev/ttyUSB0"],
            serial_factory=factory,
            port_provider=lambda: ["/dev/ttyUSB0", "/dev/ttyACM0"],
        )
        receiver.start()
        self.assertTrue(wait_until(lambda: receiver.active_port == "/dev/ttyACM0"))
        receiver.stop()

        self.assertEqual(opened_ports, ["/dev/ttyACM0"])


if __name__ == "__main__":
    unittest.main()
