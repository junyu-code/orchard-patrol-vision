# HTTP 的 TCP 发送
import socket
import threading
import json

class TCPSender:
    """
    直接发 HTTP 的 TCPSender
    """
    def __init__(self, host='0.0.0.0', port=8080):
        self.host = host
        self.port = port
        self.server_socket = None
        self.client_socket = None
        self.client_address = None
        self.is_running = False

    def start_server(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(1)
            self.is_running = True
            print(f"TCP HTTP 服务器已启动: {self.host}:{self.port}")

            threading.Thread(target=self._accept_thread, daemon=True).start()
            return True
        except Exception as e:
            print(f"启动失败: {e}")
            return False

    def _accept_thread(self):
        while self.is_running:
            try:
                self.server_socket.settimeout(1.0)
                sock, addr = self.server_socket.accept()
                self.client_socket = sock
                self.client_address = addr
                print(f"客户端已连接: {addr}")
            except socket.timeout:
                continue

    def send_robot_with_disease(
        self,
        robot_id, robot_status, frame_index,
        left_tree_index, right_tree_index,
        hour, minute, second,
        lat_degree, lat_minute, lat_second, lat_direction,
        lon_degree, lon_minute, lon_second, lon_direction,
        azimuth, velocity, eyepoint_height, bat_voltage, soc,

        conf1, count1,
        conf2, count2,
        conf3, count3
    ):
        if not self.client_socket:
            return False

        try:
            # 把所有数据拼成 JSON（HTTP 最喜欢）
            data = {
                "robot_id": robot_id,
                "status": robot_status,
                "frame": frame_index,
                "tree_left": left_tree_index,
                "tree_right": right_tree_index,
                "time": f"{hour:02d}:{minute:02d}:{second:02d}",
                "gps_lat": (lat_degree, lat_minute, lat_second, lat_direction),
                "gps_lon": (lon_degree, lon_minute, lon_second, lon_direction),
                "azimuth": azimuth,
                "velocity": velocity,
                "camera_height": eyepoint_height,
                "voltage": bat_voltage,
                "soc": soc,

                # 病虫害：顺序代表ID
                "disease_1": {"conf": conf1, "count": count1},
                "disease_2": {"conf": conf2, "count": count2},
                "disease_3": {"conf": conf3, "count": count3},
            }

            # 转成 JSON 字符串
            body = json.dumps(data, ensure_ascii=False)
            body_bytes = body.encode('utf-8')

            # 构造标准 HTTP 响应
            http_response = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: application/json; charset=utf-8\r\n"
                b"Connection: keep-alive\r\n"
                b"Content-Length: " + str(len(body_bytes)).encode() + b"\r\n"
                b"\r\n"
            ) + body_bytes

            # 发送
            self.client_socket.sendall(http_response)
            return True

        except Exception as e:
            print(f"HTTP 发送失败: {e}")
            self.client_socket = None
            return False

    def stop(self):
        self.is_running = False
        if self.client_socket:
            self.client_socket.close()
        if self.server_socket:
            self.server_socket.close()
        print("TCP HTTP 服务已停止")