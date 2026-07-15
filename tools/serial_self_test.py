#!/usr/bin/env python3
"""统一电控遥测、旧 OPGPS 和串口物理链路自测工具。"""

import argparse
import os
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    print("自测需要 pyserial>=3.5，请先安装项目依赖", file=sys.stderr)
    raise SystemExit(2)

from transport.gps_serial_receiver import GpsSerialReceiver
from transport.gps_protocol import calculate_checksum
from transport.serial_sender import SerialSender
from transport.telemetry_protocol import (
    DEFINED_FLAGS_MASK,
    FLAG_SOC,
    TelemetryStreamBuffer,
    build_telemetry_packet,
    unpack_telemetry_packet,
)
from transport.telemetry_serial_receiver import TelemetrySerialReceiver


def _serial_for_url_factory(**kwargs):
    port = kwargs.pop("port")
    return serial.serial_for_url(port, **kwargs)


def _read_exact(connection, size: int, timeout: float) -> bytes:
    deadline = time.monotonic() + timeout
    received = bytearray()
    while len(received) < size and time.monotonic() < deadline:
        chunk = connection.read(size - len(received))
        if chunk:
            received.extend(chunk)
    return bytes(received)


def _physical_serial(port: str, baudrate: int, timeout: float):
    options = {
        "port": port,
        "baudrate": baudrate,
        "bytesize": serial.EIGHTBITS,
        "parity": serial.PARITY_NONE,
        "stopbits": serial.STOPBITS_ONE,
        "timeout": min(0.1, timeout),
        "write_timeout": timeout,
        "xonxoff": False,
        "rtscts": False,
        "dsrdtr": False,
    }
    if os.name == "posix":
        options["exclusive"] = True
    return serial.Serial(**options)


def _find_port_users(port: str):
    """查找当前用户中占用 Linux 串口文件描述符的进程。"""
    if os.name != "posix" or not Path("/proc").is_dir():
        return []

    target = os.path.realpath(port)
    current_pid = os.getpid()
    users = []
    for process_dir in Path("/proc").iterdir():
        if not process_dir.name.isdigit():
            continue
        pid = int(process_dir.name)
        if pid == current_pid:
            continue
        try:
            matches = any(
                os.path.realpath(os.readlink(fd_path)) == target
                for fd_path in (process_dir / "fd").iterdir()
            )
        except (FileNotFoundError, PermissionError, OSError):
            continue
        if not matches:
            continue
        try:
            command = (process_dir / "cmdline").read_bytes()
            command = command.replace(b"\0", b" ").decode("utf-8", errors="replace").strip()
        except (FileNotFoundError, PermissionError, OSError):
            command = "<无法读取命令行>"
        users.append((pid, command))
    return users


def _build_cross_packet(direction: str, sequence: int) -> bytes:
    body = f"ORCHARD|{direction}|{sequence:02d}".encode("ascii")
    return b"\x55\xaa" + body + bytes([sum(body) & 0xFF]) + b"\r\n"


def _test_cross_direction(sender, receiver, direction: str, count: int, timeout: float):
    sender.reset_output_buffer()
    receiver.reset_input_buffer()
    passed = 0
    for index in range(count):
        expected = _build_cross_packet(direction, index)
        written = sender.write(expected)
        sender.flush()
        actual = _read_exact(receiver, len(expected), timeout)
        success = written == len(expected) and actual == expected
        passed += int(success)
        state = "通过" if success else "失败"
        print(
            f"  [{index + 1}/{count}] {state}："
            f"发送 {written}/{len(expected)} 字节，接收 {len(actual)} 字节"
        )
        if not success:
            print(f"    期望：{expected.hex(' ')}")
            print(f"    收到：{actual.hex(' ') or '<空>'}")
        time.sleep(0.05)
    return passed


def _test_opgps_pipeline(
    sender_port: str,
    receiver_port: str,
    baudrate: int,
    timeout: float,
    packet_count: int,
) -> bool:
    # 项目接收线程接管端口前，清除双向交叉测试遗留的字节。
    with _physical_serial(receiver_port, baudrate, timeout) as connection:
        connection.reset_input_buffer()

    receiver = GpsSerialReceiver(
        port=receiver_port,
        baudrate=baudrate,
        read_timeout=min(0.1, timeout),
        stale_timeout=max(2.0, timeout * 2),
        reconnect_interval=0.2,
        auto_detect=False,
    )
    receiver.start()
    try:
        ready_deadline = time.monotonic() + timeout
        while receiver.active_port is None and time.monotonic() < ready_deadline:
            time.sleep(0.02)
        if receiver.active_port is None:
            print("  失败：项目 GPS 接收线程未能打开接收端口")
            return False

        with _physical_serial(sender_port, baudrate, timeout) as sender:
            for index in range(packet_count):
                sequence = 1000 + index
                body = (
                    f"OPGPS,V1,Robot_001,{sequence},110.29557332,25.06143046,"
                    "52.4,2,12,0.8"
                )
                packet = f"${body}*{calculate_checksum(body):02X}\r\n".encode("ascii")
                sender.write(packet)
                sender.flush()
                time.sleep(0.08)

        receive_deadline = time.monotonic() + max(1.0, timeout)
        while (
            receiver.get_stats()["valid_packets"] < packet_count
            and time.monotonic() < receive_deadline
        ):
            time.sleep(0.02)

        stats = receiver.get_stats()
        snapshot = receiver.get_snapshot()
        latest_sequence = snapshot.fix.sequence if snapshot.fix is not None else None
        expected_sequence = 1000 + packet_count - 1
        print(
            "  OPGPS 统计："
            f"有效={stats['valid_packets']}，协议错误={stats['protocol_errors']}，"
            f"校验错误={stats['checksum_errors']}，最新序号={latest_sequence}"
        )
        return (
            stats["valid_packets"] == packet_count
            and stats["protocol_errors"] == 0
            and stats["checksum_errors"] == 0
            and snapshot.valid
            and latest_sequence == expected_sequence
        )
    finally:
        receiver.stop()


def _build_standard_telemetry_packet(sequence: int) -> bytes:
    tree_id = 1 + (int(sequence) % 100) * 2
    return build_telemetry_packet(
        sequence=sequence & 0xFFFF,
        robot_id=1,
        robot_status=1,
        valid_flags=DEFINED_FLAGS_MASK,
        route_id=1,
        waypoint_id=10,
        current_tree_id=tree_id,
        left_tree_id=tree_id,
        right_tree_id=tree_id + 1,
        camera_side=1,
        gps_fix=4,
        satellites=12,
        hdop_x100=52,
        longitude_e7=1_102_955_733,
        latitude_e7=250_614_305,
        altitude_cm=14_048,
        timestamp=1_721_000_000 + sequence,
        azimuth_x100=9_000,
        velocity_mm_s=1_200,
        camera_height_mm=1_500,
        battery_mv=24_000,
        soc=85,
        fault_code=0,
    )


def _test_telemetry_pipeline(
    sender_port: str,
    receiver_port: str,
    baudrate: int,
    timeout: float,
    packet_count: int,
) -> bool:
    """通过两个交叉连接的串口验证统一遥测接收器。"""
    with _physical_serial(receiver_port, baudrate, timeout) as connection:
        connection.reset_input_buffer()

    receiver = TelemetrySerialReceiver(
        port=receiver_port,
        baudrate=baudrate,
        read_timeout=min(0.1, timeout),
        stale_timeout=max(2.0, timeout * 2),
        reconnect_interval=0.2,
        auto_detect=False,
    )
    receiver.start()
    try:
        ready_deadline = time.monotonic() + timeout
        while receiver.active_port is None and time.monotonic() < ready_deadline:
            time.sleep(0.02)
        if receiver.active_port is None:
            print("  失败：统一遥测接收线程未能打开接收端口")
            return False

        with _physical_serial(sender_port, baudrate, timeout) as sender:
            for index in range(packet_count):
                sender.write(_build_standard_telemetry_packet(2000 + index))
                sender.flush()
                time.sleep(0.08)

        receive_deadline = time.monotonic() + max(1.0, timeout)
        while (
            receiver.get_stats()["valid_packets"] < packet_count
            and time.monotonic() < receive_deadline
        ):
            time.sleep(0.02)

        stats = receiver.get_stats()
        snapshot = receiver.get_snapshot()
        latest_sequence = (
            snapshot.telemetry.sequence if snapshot.telemetry is not None else None
        )
        expected_sequence = (2000 + packet_count - 1) & 0xFFFF
        print(
            "  遥测统计："
            f"有效={stats['valid_packets']}，协议错误={stats['protocol_errors']}，"
            f"CRC错误={stats['checksum_errors']}，最新序号={latest_sequence}"
        )
        return (
            stats["valid_packets"] == packet_count
            and stats["protocol_errors"] == 0
            and stats["checksum_errors"] == 0
            and snapshot.valid
            and latest_sequence == expected_sequence
        )
    finally:
        receiver.stop()


def run_dual_port_test(
    sender_port: str,
    receiver_port: str,
    baudrate: int,
    timeout: float,
    count: int,
    verify_telemetry: bool = True,
    verify_opgps: bool = True,
) -> int:
    """验证双串口物理链路、统一遥测和旧 OPGPS 解析。"""
    if count <= 0:
        raise ValueError("测试次数必须大于 0")
    if timeout <= 0:
        raise ValueError("读取超时必须大于 0")
    if os.path.realpath(sender_port) == os.path.realpath(receiver_port):
        raise ValueError("双串口测试必须指定两个不同端口")

    print("[1/5] 检查设备与端口占用")
    busy = False
    for port in (sender_port, receiver_port):
        if os.name == "posix" and not Path(port).exists():
            print(f"  失败：设备不存在 {port}")
            busy = True
            continue
        users = _find_port_users(port)
        if users:
            busy = True
            for pid, command in users:
                print(f"  失败：{port} 被 PID {pid} 占用：{command}")
        else:
            print(f"  可用：{port}")
    if busy:
        print("请先停止占用串口的主程序或服务，再重新测试。")
        return 2

    with _physical_serial(sender_port, baudrate, timeout) as sender, _physical_serial(
        receiver_port, baudrate, timeout
    ) as serial_b:
        print(f"[2/5] 模拟发送端 {sender_port} -> 项目接收端 {receiver_port}")
        sender_to_receiver = _test_cross_direction(
            sender, serial_b, "TX->RX", count, timeout
        )
        print(f"[3/5] 硬件反向校验 {receiver_port} -> {sender_port}")
        receiver_to_sender = _test_cross_direction(
            serial_b, sender, "RX->TX", count, timeout
        )
        sender.reset_input_buffer()
        serial_b.reset_input_buffer()

    telemetry_ok = True
    if verify_telemetry:
        print(f"[4/5] 统一遥测接收链路：{sender_port} -> {receiver_port}")
        telemetry_ok = _test_telemetry_pipeline(
            sender_port=sender_port,
            receiver_port=receiver_port,
            baudrate=baudrate,
            timeout=timeout,
            packet_count=min(count, 5),
        )
    else:
        print("[4/5] 已跳过统一遥测解析")

    opgps_ok = True
    if verify_opgps:
        print(f"[5/5] 旧 OPGPS 接收链路：{sender_port} -> {receiver_port}")
        opgps_ok = _test_opgps_pipeline(
            sender_port=sender_port,
            receiver_port=receiver_port,
            baudrate=baudrate,
            timeout=timeout,
            packet_count=min(count, 5),
        )
    else:
        print("[5/5] 已跳过旧 OPGPS 解析")

    print("=" * 52)
    print(
        f"物理链路：发送->接收 {sender_to_receiver}/{count}，"
        f"反向 {receiver_to_sender}/{count}"
    )
    print(f"统一遥测接收：{'通过' if telemetry_ok else '失败'}")
    print(f"旧 GPS 接收：{'通过' if opgps_ok else '失败'}")
    passed = (
        sender_to_receiver == count
        and receiver_to_sender == count
        and telemetry_ok
        and opgps_ok
    )
    print(f"最终结论：{'串口链路正常' if passed else '串口链路异常'}")
    return 0 if passed else 1


def list_serial_ports() -> int:
    ports = list(list_ports.comports())
    if not ports:
        print("未发现物理串口")
        return 1

    print(f"发现 {len(ports)} 个串口：")
    for item in ports:
        print(f"  {item.device} | {item.description} | {item.hwid}")
    return 0


def run_loopback(
    port: str,
    baudrate: int,
    timeout: float,
    count: int,
    disease_id: int,
    confidence: float,
) -> int:
    """发送真实项目帧，并要求回环数据逐字节一致。"""
    if count <= 0:
        raise ValueError("测试次数必须大于 0")

    sender = SerialSender(
        port=port,
        baudrate=baudrate,
        timeout=timeout,
        serial_factory=_serial_for_url_factory,
    )
    if not sender.open_serial():
        return 2

    passed = 0
    try:
        if hasattr(sender.ser, "reset_input_buffer"):
            sender.ser.reset_input_buffer()

        for index in range(count):
            current_id = (int(disease_id) + index) % 256
            expected = SerialSender.build_frame(current_id, confidence)
            if not sender.pack_and_send(current_id, confidence):
                print(f"[{index + 1}/{count}] 失败：发送未完成")
                continue

            actual = _read_exact(sender.ser, len(expected), timeout)
            if actual == expected:
                passed += 1
                print(f"[{index + 1}/{count}] 通过：{actual.hex(' ')}")
            else:
                print(
                    f"[{index + 1}/{count}] 失败：期望 {expected.hex(' ')}，"
                    f"收到 {actual.hex(' ') or '<空>'}"
                )
    finally:
        sender.close_serial()

    print(f"回环自测结果：{passed}/{count} 通过")
    return 0 if passed == count else 1


def run_telemetry_loopback(port: str, baudrate: int, timeout: float, count: int) -> int:
    """发送并回读项目标准遥测包，再使用正式协议解析器校验。"""
    if count <= 0:
        raise ValueError("测试次数必须大于 0")
    if "://" in port:
        connection = serial.serial_for_url(
            port,
            baudrate=baudrate,
            timeout=min(0.1, timeout),
            write_timeout=timeout,
        )
    else:
        connection = _physical_serial(port, baudrate, timeout)

    passed = 0
    stream = TelemetryStreamBuffer()
    try:
        connection.reset_input_buffer()
        for index in range(count):
            expected = _build_standard_telemetry_packet(index + 1)
            written = connection.write(expected)
            connection.flush()
            actual = _read_exact(connection, len(expected), timeout)
            packets = stream.feed(actual)
            success = (
                written == len(expected)
                and actual == expected
                and len(packets) == 1
                and packets[0].sequence == index + 1
            )
            if success:
                passed += 1
                print(
                    f"[{index + 1}/{count}] 通过：58 字节，"
                    f"CRC={actual[54:56].hex().upper()}"
                )
            else:
                print(
                    f"[{index + 1}/{count}] 失败：发送={written}，"
                    f"接收={len(actual)}，解析={len(packets)}"
                )
    finally:
        connection.close()

    print(f"统一遥测回环结果：{passed}/{count} 通过")
    return 0 if passed == count else 1


def monitor_gps(port: str, baudrate: int, duration: float, min_packets: int) -> int:
    """监听 GPS 串口，并通过项目解析代码校验报文。"""
    if duration <= 0:
        raise ValueError("监听时间必须大于 0")
    if min_packets <= 0:
        raise ValueError("最少报文数必须大于 0")

    auto_detect = port.strip().upper() == "AUTO"
    receiver = GpsSerialReceiver(
        port="" if auto_detect else port,
        baudrate=baudrate,
        auto_detect=auto_detect,
        reconnect_interval=0.5,
        probe_timeout=min(1.5, duration),
    )
    receiver.start()
    deadline = time.monotonic() + duration
    last_sequence = None
    print(f"开始监听 GPS：{port} @ {baudrate}，持续 {duration:g} 秒")
    try:
        while time.monotonic() < deadline:
            snapshot = receiver.get_snapshot()
            if snapshot.fix is not None and snapshot.fix.sequence != last_sequence:
                fix = snapshot.fix
                last_sequence = fix.sequence
                print(
                    f"报文 #{fix.sequence}：robot={fix.robot_id}，"
                    f"lon={fix.longitude:.8f}，lat={fix.latitude:.8f}，"
                    f"quality={fix.fix_quality}，satellites={fix.satellites}"
                )
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("用户终止监听")
    finally:
        receiver.stop()

    stats = receiver.get_stats()
    valid_packets = stats["valid_packets"]
    print(
        "GPS 自测统计："
        f"有效={valid_packets}，协议错误={stats['protocol_errors']}，"
        f"校验错误={stats['checksum_errors']}，读取错误={stats['read_failures']}，"
        f"连接失败={stats['connect_failures']}"
    )
    if valid_packets < min_packets:
        print(f"GPS 自测失败：有效报文少于 {min_packets} 条")
        return 1
    print("GPS 自测通过")
    return 0


def monitor_telemetry(port: str, baudrate: int, duration: float, min_packets: int) -> int:
    """监听真实电控串口并通过正式 58 字节接收器校验。"""
    if duration <= 0:
        raise ValueError("监听时间必须大于 0")
    if min_packets <= 0:
        raise ValueError("最少报文数必须大于 0")

    auto_detect = port.strip().upper() == "AUTO"
    receiver = TelemetrySerialReceiver(
        port="" if auto_detect else port,
        baudrate=baudrate,
        auto_detect=auto_detect,
        reconnect_interval=0.5,
        probe_timeout=min(1.5, duration),
    )
    receiver.start()
    deadline = time.monotonic() + duration
    last_sequence = None
    print(f"开始监听统一遥测：{port} @ {baudrate}，持续 {duration:g} 秒")
    try:
        while time.monotonic() < deadline:
            snapshot = receiver.get_snapshot()
            data = snapshot.telemetry
            if data is not None and data.sequence != last_sequence:
                last_sequence = data.sequence
                speed = snapshot.to_status_data().get("velocity")
                speed_text = "--" if speed is None else f"{speed:.2f}m/s"
                print(
                    f"报文 #{data.sequence}：robot={data.robot_id}，"
                    f"status={data.robot_status}，tree={data.current_tree_id}/"
                    f"{data.left_tree_id}/{data.right_tree_id}，speed={speed_text}，"
                    f"soc={data.soc if data.has(FLAG_SOC) else '--'}"
                )
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("用户终止监听")
    finally:
        receiver.stop()

    stats = receiver.get_stats()
    print(
        "遥测自测统计："
        f"有效={stats['valid_packets']}，协议错误={stats['protocol_errors']}，"
        f"CRC错误={stats['checksum_errors']}，读取错误={stats['read_failures']}，"
        f"连接失败={stats['connect_failures']}"
    )
    if stats["valid_packets"] < min_packets:
        print(f"遥测自测失败：有效报文少于 {min_packets} 条")
        return 1
    print("遥测自测通过")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="果园巡检项目串口自测")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="列出当前物理串口")

    loopback = subparsers.add_parser(
        "loopback",
        help="发送并回读病害帧；物理串口需要短接 TX/RX",
    )
    loopback.add_argument("--port", default="loop://", help="串口或 URL，默认 loop://")
    loopback.add_argument("--baudrate", type=int, default=9600)
    loopback.add_argument("--timeout", type=float, default=1.0)
    loopback.add_argument("--count", type=int, default=3)
    loopback.add_argument("--disease-id", type=int, default=5)
    loopback.add_argument("--confidence", type=float, default=0.85)

    telemetry_loopback = subparsers.add_parser(
        "telemetry-loopback",
        help="发送并回读 58 字节统一遥测包；物理串口需要短接 TX/RX",
    )
    telemetry_loopback.add_argument("--port", default="loop://")
    telemetry_loopback.add_argument("--baudrate", type=int, default=9600)
    telemetry_loopback.add_argument("--timeout", type=float, default=1.0)
    telemetry_loopback.add_argument("--count", type=int, default=3)

    telemetry = subparsers.add_parser("telemetry", help="监听并校验 58 字节电控统一遥测")
    telemetry.add_argument("--port", required=True, help="遥测串口，或 AUTO 自动查找")
    telemetry.add_argument("--baudrate", type=int, default=9600)
    telemetry.add_argument("--duration", type=float, default=10.0)
    telemetry.add_argument("--min-packets", type=int, default=1)

    gps = subparsers.add_parser("gps", help="监听并校验项目 OPGPS 报文")
    gps.add_argument("--port", required=True, help="GPS 串口，或 AUTO 自动查找")
    gps.add_argument("--baudrate", type=int, default=9600)
    gps.add_argument("--duration", type=float, default=10.0, help="监听秒数")
    gps.add_argument("--min-packets", type=int, default=1, help="通过所需的最少有效报文数")

    dual = subparsers.add_parser(
        "dual",
        help="验证双 USB-TTL 的双向链路、统一遥测和旧 GPS 接收",
    )
    dual.add_argument(
        "--sender-port", "--port-a", dest="sender_port", default="/dev/ttyUSB0"
    )
    dual.add_argument(
        "--receiver-port", "--port-b", dest="receiver_port", default="/dev/ttyUSB1"
    )
    dual.add_argument("--baudrate", type=int, default=9600)
    dual.add_argument("--timeout", type=float, default=1.5)
    dual.add_argument("--count", type=int, default=5)
    dual.add_argument("--skip-telemetry", action="store_true", help="跳过统一遥测解析")
    dual.add_argument("--skip-opgps", action="store_true", help="跳过旧 OPGPS 解析")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "list":
            return list_serial_ports()
        if args.command == "loopback":
            return run_loopback(
                port=args.port,
                baudrate=args.baudrate,
                timeout=args.timeout,
                count=args.count,
                disease_id=args.disease_id,
                confidence=args.confidence,
            )
        if args.command == "telemetry-loopback":
            return run_telemetry_loopback(
                port=args.port,
                baudrate=args.baudrate,
                timeout=args.timeout,
                count=args.count,
            )
        if args.command == "telemetry":
            return monitor_telemetry(
                port=args.port,
                baudrate=args.baudrate,
                duration=args.duration,
                min_packets=args.min_packets,
            )
        if args.command == "gps":
            return monitor_gps(
                port=args.port,
                baudrate=args.baudrate,
                duration=args.duration,
                min_packets=args.min_packets,
            )
        return run_dual_port_test(
            sender_port=args.sender_port,
            receiver_port=args.receiver_port,
            baudrate=args.baudrate,
            timeout=args.timeout,
            count=args.count,
            verify_telemetry=not args.skip_telemetry,
            verify_opgps=not args.skip_opgps,
        )
    except (ValueError, serial.SerialException, OSError) as exc:
        print(f"自测无法执行：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
