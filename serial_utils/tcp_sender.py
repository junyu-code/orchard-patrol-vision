# serial_utils/tcp_sender.py
import socket
import threading
import time

class TCPSender:
    """TCP发送类：打包病害ID和疑似度并发送"""
    def __init__(self, host='0.0.0.0', port=8080):
        self.host = host
        self.port = port
        self.server_socket = None
        self.client_socket = None
        self.client_address = None
        self.is_running = False
        self.listen_thread = None
        # 定义帧头帧尾，与串口保持一致以便解析
        self.FRAME_HEAD = 0xFF
        self.FRAME_TAIL = 0xFE

    def start_server(self):
        """启动TCP服务器，等待客户端连接"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(1)
            self.is_running = True
            print(f"TCP服务器已启动，监听 {self.host}:{self.port} ...")
            
            # 启动线程等待连接
            self.listen_thread = threading.Thread(target=self._accept_connection, daemon=True)
            self.listen_thread.start()
            return True
        except Exception as e:
            print(f"TCP服务器启动失败：{e}")
            self.is_running = False
            return False

    def _accept_connection(self):
        """接受客户端连接的后台线程"""
        while self.is_running:
            try:
                self.server_socket.settimeout(1.0) # 设置超时以便能检查 is_running
                client_socket, client_address = self.server_socket.accept()
                self.client_socket = client_socket
                self.client_address = client_address
                print(f"客户端已连接：{client_address}")
                
                # 注意：这里简化处理，只保持最新的一个连接。
                # 如果需要多连接，需要更复杂的管理逻辑。
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.is_running:
                    print(f"接受连接错误：{e}")
                break

    def pack_and_send(self, disease_id, confidence):
        """打包并发送数据"""
        if not self.client_socket:
            return False
        
        try:
            disease_id = int(disease_id)
            if disease_id < 0 or disease_id > 255:
                raise ValueError(f"病害ID超出范围：{disease_id}")
            
            confidence = min(max(float(confidence), 0.0), 1.0)
            conf_int = int(confidence * 255)

            # 打包: FrameHead + ID + Conf + FrameTail
            data = bytes([self.FRAME_HEAD, disease_id, conf_int, self.FRAME_TAIL])
            
            self.client_socket.sendall(data)
            return True
        except Exception as e:
            print(f"TCP发送失败：{e}")
            self.client_socket = None # 断开连接，等待重连
            return False

    def stop(self):
        """停止TCP服务"""
        self.is_running = False
        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        print("TCP服务已停止")