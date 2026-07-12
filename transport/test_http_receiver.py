import socket
import threading

def handle_client(conn, addr):
    print(f"\n【连接来自】: {addr}")
    while True:
        data = conn.recv(4096)
        if not data:
            break
        print("\n========== 收到 HTTP 数据 ==========")
        print(data.decode('utf-8', errors='replace'))
        print("====================================\n")
    conn.close()

def run_server(host='0.0.0.0', port=8080):
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)
    print(f"HTTP 测试服务器已启动：{host}:{port}")
    print("等待 YOLO 程序发送数据...\n")

    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

if __name__ == '__main__':
    run_server(port=8080)