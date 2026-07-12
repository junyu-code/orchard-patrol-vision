# 小demo，实际发送还要做一下筛选，置信度高于一定阈值我才发送，否则就不发送，而且最好一次统计一帧画面中有多少个病虫害
import serial
import serial.tools.list_ports
import time

class SerialSender:
    """串口发送类：打包病害ID（高8位）和疑似度（低8位）并发送（添加帧头帧尾）"""
    def __init__(self, port=None, baudrate=9600, timeout=1):
        self.ser = None
        self.port = port  # 串口端口（如COM3、/dev/ttyUSB0）
        self.baudrate = baudrate  # 波特率，默认9600
        self.timeout = timeout    # 超时时间
        self.is_open = False      # 串口是否打开
        # 新增：定义帧头帧尾（和STM32端一致）
        self.FRAME_HEAD = 0xFF    # 帧头
        self.FRAME_TAIL = 0xFE    # 帧尾

    def open_serial(self):
        """打开串口，自动检测可用串口（未指定port时）"""
        try:
            # 未指定端口时，自动检测第一个可用串口
            if not self.port:
                ports = list(serial.tools.list_ports.comports())
                if not ports:
                    raise Exception("未检测到可用串口！")
                self.port = ports[0].device  # 取第一个可用串口
            
            # 初始化串口（参数和STM32一致：8N1）
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                parity=serial.PARITY_NONE,  # 无校验
                stopbits=serial.STOPBITS_ONE,  # 1位停止位
                bytesize=serial.EIGHTBITS,  # 8位数据位
                timeout=self.timeout
            )
            self.is_open = True
            print(f"串口已打开：{self.port}，波特率：{self.baudrate}")
            return True
        except Exception as e:
            print(f"串口打开失败：{e}")
            self.is_open = False
            return False

    def pack_and_send(self, disease_id, confidence):
        """
        打包并发送数据（符合STM32解析格式）：
        - 最终发送格式：0xFF（帧头） + 病害ID字节 + 疑似度字节 + 0xFE（帧尾）
        - disease_id：病害ID（0-255，1字节）
        - confidence：疑似度（0-1浮点数，转换为0-255整数）
        """
        if not self.is_open or self.ser is None:
            print("串口未打开，发送失败！")
            return False
        
        try:
            # 1. 数据校验与转换
            disease_id = int(disease_id)
            if disease_id < 0 or disease_id > 255:
                raise ValueError(f"病害ID超出范围（0-255）：{disease_id}")
            
            # 疑似度（0-1）转换为0-255整数
            confidence = min(max(float(confidence), 0.0), 1.0)  # 限制0-1
            conf_int = int(confidence * 255)  # 0→0，1→255

            # 2. 打包为完整数据包（帧头 + 2字节数据 + 帧尾）
            frame_head = self.FRAME_HEAD.to_bytes(1, byteorder='big')  # 帧头0xFF
            high_byte = disease_id.to_bytes(1, byteorder='big')        # 病害ID字节
            low_byte = conf_int.to_bytes(1, byteorder='big')           # 疑似度字节
            frame_tail = self.FRAME_TAIL.to_bytes(1, byteorder='big')  # 帧尾0xFE
            
            # 3. 发送完整数据包（关键！）
            self.ser.write(frame_head + high_byte + low_byte + frame_tail)
            time.sleep(0.001)  # 微小延时，避免串口粘包
            print(f"串口发送成功 | 完整数据包：0x{frame_head.hex()} 0x{high_byte.hex()} 0x{low_byte.hex()} 0x{frame_tail.hex()}")
            print(f"解析：病害ID={disease_id}，疑似度={confidence:.2f}（0x{low_byte.hex()}）")
            return True
        
        except Exception as e:
            print(f"串口发送失败：{e}")
            return False

    def close_serial(self):
        """关闭串口"""
        if self.ser and self.is_open:
            self.ser.close()
            self.is_open = False
            print("串口已关闭")

    def __del__(self):
        """析构函数：程序退出时自动关闭串口"""
        self.close_serial()

# 测试代码（单独运行serial.py时验证）
if __name__ == "__main__":
    # 示例：发送病害ID=5，疑似度=0.85（替换为你的实际串口端口，如COM3、COM13）
    sender = SerialSender(port="COM13", baudrate=9600)  
    if sender.open_serial():
        sender.pack_and_send(disease_id=5, confidence=0.85)
        sender.close_serial()