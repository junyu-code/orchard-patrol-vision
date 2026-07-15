"""Disease detection serial frame sender."""

import math
from typing import Callable, Iterable, Optional

import serial
from serial.tools import list_ports


class SerialSender:
    """Send ``head + disease ID + confidence + tail`` frames over serial."""

    FRAME_HEAD = 0xFF
    FRAME_TAIL = 0xFE

    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = 9600,
        timeout: float = 1,
        serial_factory: Optional[Callable] = None,
        port_provider: Optional[Callable[[], Iterable]] = None,
    ):
        self.ser = None
        self.port = str(port).strip() if port else None
        self.baudrate = int(baudrate)
        self.timeout = float(timeout)
        if self.baudrate <= 0:
            raise ValueError("串口波特率必须大于 0")
        if self.timeout < 0:
            raise ValueError("串口超时时间不能小于 0")

        self.serial_factory = serial_factory or serial.Serial
        self.port_provider = port_provider or list_ports.comports
        self.is_open = False

    @classmethod
    def build_frame(cls, disease_id, confidence) -> bytes:
        """Build one STM32-compatible four-byte disease frame."""
        disease_id = int(disease_id)
        if not 0 <= disease_id <= 255:
            raise ValueError(f"病害ID超出范围（0-255）：{disease_id}")

        confidence = float(confidence)
        if not math.isfinite(confidence):
            raise ValueError("疑似度必须是有限数字")
        confidence = min(max(confidence, 0.0), 1.0)
        confidence_byte = int(confidence * 255)
        return bytes((cls.FRAME_HEAD, disease_id, confidence_byte, cls.FRAME_TAIL))

    def open_serial(self) -> bool:
        """Open the configured port, or the first enumerated port when omitted."""
        self.close_serial(verbose=False)
        connection = None
        try:
            if not self.port:
                ports = list(self.port_provider() or [])
                if not ports:
                    raise RuntimeError("未检测到可用串口")
                self.port = str(getattr(ports[0], "device", ports[0]))

            connection = self.serial_factory(
                port=self.port,
                baudrate=self.baudrate,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS,
                timeout=self.timeout,
                write_timeout=self.timeout,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )
            if hasattr(connection, "is_open") and not connection.is_open:
                connection.open()

            self.ser = connection
            self.is_open = True
            print(f"串口已打开：{self.port}，波特率：{self.baudrate}")
            return True
        except Exception as exc:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
            self.ser = None
            self.is_open = False
            print(f"串口打开失败：{exc}")
            return False

    def pack_and_send(self, disease_id, confidence) -> bool:
        """Build and send one disease frame; return whether all bytes were written."""
        if not self.is_open or self.ser is None:
            print("串口未打开，发送失败")
            return False

        try:
            frame = self.build_frame(disease_id, confidence)
            written = self.ser.write(frame)
            if written != len(frame):
                raise serial.SerialTimeoutException(
                    f"串口短写：应发送 {len(frame)} 字节，实际发送 {written} 字节"
                )
            self.ser.flush()
            normalized_confidence = frame[2] / 255.0
            print(
                f"串口发送成功 | 数据包：{' '.join(f'0x{value:02x}' for value in frame)} | "
                f"病害ID={frame[1]}，疑似度={normalized_confidence:.2f}"
            )
            return True
        except Exception as exc:
            print(f"串口发送失败：{exc}")
            return False

    def close_serial(self, verbose: bool = True) -> bool:
        """Close the current connection and reset sender state."""
        connection = self.ser
        was_open = self.is_open or connection is not None
        self.ser = None
        self.is_open = False
        if connection is None:
            return True

        try:
            connection.close()
            if verbose and was_open:
                print("串口已关闭")
            return True
        except Exception as exc:
            if verbose:
                print(f"串口关闭失败：{exc}")
            return False

    def __del__(self):
        try:
            self.close_serial(verbose=False)
        except Exception:
            pass
