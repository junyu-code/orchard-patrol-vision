"""
最简单的连接测试 - 只测试基本网络连通性
"""

import socket
import sys

# 设置 UTF-8 编码
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

print("=" * 50)
print("简单连接测试")
print("=" * 50)

# 测试1: UDP
print("\n[UDP 测试]")
UDP_HOST = "1.15.149.164"
UDP_PORT = 4926

try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    test_data = b"TEST"
    sock.sendto(test_data, (UDP_HOST, UDP_PORT))
    print(f"[OK] UDP 发送成功: {UDP_HOST}:{UDP_PORT}")
    sock.close()
except Exception as e:
    print(f"[FAIL] UDP 失败: {e}")

# 测试2: RTMP (TCP)
print("\n[RTMP 测试]")
RTMP_HOST = "www.xsjny.com"
RTMP_PORT = 1935

try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    sock.connect((RTMP_HOST, RTMP_PORT))
    print(f"[OK] RTMP 端口可达: {RTMP_HOST}:{RTMP_PORT}")
    sock.close()
except Exception as e:
    print(f"[FAIL] RTMP 失败: {e}")

print("\n" + "=" * 50)
