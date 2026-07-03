"""
甲方B连接测试脚本
测试 UDP 和 RTMP 连接是否正常
"""

import socket
import time
import sys
from datetime import datetime

# Windows 控制台编码设置
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# 添加当前目录到路径
sys.path.insert(0, '.')

print("=" * 60)
print("甲方B连接测试")
print("=" * 60)

# ========== 测试1: UDP 连接 ==========
print("\n【测试1】UDP 连接测试")
print("-" * 60)

UDP_HOST = "1.15.149.164"
UDP_PORT = 4926

try:
    print(f"📡 尝试连接 UDP: {UDP_HOST}:{UDP_PORT}")

    # 创建 UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5)  # 5秒超时

    # 发送测试数据包（28字节，符合协议格式）
    test_packet = b'\x66' + b'\x00' * 26 + b'\x99'

    print(f"📤 发送测试数据包 ({len(test_packet)} 字节)...")
    sock.sendto(test_packet, (UDP_HOST, UDP_PORT))

    print("✅ UDP 数据包发送成功！")
    print(f"   目标: {UDP_HOST}:{UDP_PORT}")
    print(f"   数据: {test_packet.hex()}")

    # 尝试接收响应（UDP通常不需要响应，这里只是尝试）
    try:
        sock.settimeout(2)
        data, addr = sock.recvfrom(1024)
        print(f"✅ 收到服务器响应: {data.hex()} from {addr}")
    except socket.timeout:
        print("⚠️  未收到响应（正常，UDP 通常不响应）")

    sock.close()
    udp_ok = True

except socket.timeout:
    print("❌ UDP 连接超时")
    print("   可能原因：")
    print("   1. 服务器地址或端口错误")
    print("   2. 防火墙阻止了 UDP 流量")
    print("   3. 服务器未运行")
    udp_ok = False

except Exception as e:
    print(f"❌ UDP 连接失败: {e}")
    print(f"   错误类型: {e.__class__.__name__}")
    udp_ok = False

# ========== 测试2: RTMP 连接 ==========
print("\n【测试2】RTMP 服务器连接测试")
print("-" * 60)

RTMP_URL = "rtmp://www.xsjny.com/live/robot1_sensor1"
RTMP_HOST = "www.xsjny.com"
RTMP_PORT = 1935  # RTMP 默认端口

try:
    print(f"🎬 尝试连接 RTMP 服务器: {RTMP_HOST}:{RTMP_PORT}")

    # 测试 TCP 连接（RTMP 基于 TCP）
    tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_sock.settimeout(5)

    print(f"🔌 尝试 TCP 连接到 {RTMP_HOST}:{RTMP_PORT}...")
    tcp_sock.connect((RTMP_HOST, RTMP_PORT))

    print("✅ RTMP 服务器端口可达！")
    print(f"   推流地址: {RTMP_URL}")

    tcp_sock.close()
    rtmp_ok = True

except socket.timeout:
    print("❌ RTMP 连接超时")
    print("   可能原因：")
    print("   1. 服务器地址错误")
    print("   2. RTMP 服务未启动")
    print("   3. 防火墙阻止了连接")
    rtmp_ok = False

except socket.gaierror as e:
    print(f"❌ 域名解析失败: {e}")
    print(f"   无法解析域名: {RTMP_HOST}")
    rtmp_ok = False

except Exception as e:
    print(f"❌ RTMP 连接失败: {e}")
    print(f"   错误类型: {e.__class__.__name__}")
    rtmp_ok = False

# ========== 测试3: 使用实际模块测试 ==========
print("\n【测试3】实际模块功能测试")
print("-" * 60)

try:
    print("📦 导入 transport.udp_sender...")
    from transport.udp_sender import UdpSender

    print("📦 导入 transport.rtmp_sender...")
    from transport.rtmp_sender import RtmpSender

    print("✅ 模块导入成功")

    # 测试 UDP Sender
    print("\n🧪 测试 UdpSender 初始化...")
    udp_sender = UdpSender(
        udp_host=UDP_HOST,
        udp_port=UDP_PORT,
        robot_id=1,
        sensor_id=1
    )

    print("📤 发送测试数据...")
    success = udp_sender.send_robot_data(
        robot_status=1,
        frame_index=999,
        disease_detected=True
    )

    if success:
        print("✅ UDP 数据发送成功")
    else:
        print("❌ UDP 数据发送失败")

    udp_sender.close()
    module_ok = True

except ImportError as e:
    print(f"❌ 模块导入失败: {e}")
    print("   请确保已安装所有依赖")
    module_ok = False

except Exception as e:
    print(f"❌ 模块测试失败: {e}")
    print(f"   错误类型: {e.__class__.__name__}")
    import traceback
    traceback.print_exc()
    module_ok = False

# ========== 测试4: 网络诊断 ==========
print("\n【测试4】网络诊断")
print("-" * 60)

import subprocess
import platform

# Ping 测试
print(f"🔍 Ping 测试: {UDP_HOST}")
try:
    if platform.system().lower() == "windows":
        result = subprocess.run(
            ["ping", "-n", "4", UDP_HOST],
            capture_output=True,
            text=True,
            timeout=10
        )
    else:
        result = subprocess.run(
            ["ping", "-c", "4", UDP_HOST],
            capture_output=True,
            text=True,
            timeout=10
        )

    if result.returncode == 0:
        print("✅ Ping 成功，网络连接正常")
        # 提取关键信息
        lines = result.stdout.split('\n')
        for line in lines:
            if 'time' in line.lower() or 'ttl' in line.lower():
                print(f"   {line.strip()}")
    else:
        print("❌ Ping 失败")
        print(result.stdout)

except subprocess.TimeoutExpired:
    print("❌ Ping 超时")
except Exception as e:
    print(f"⚠️  Ping 测试出错: {e}")

# DNS 解析测试
print(f"\n🔍 DNS 解析测试: {RTMP_HOST}")
try:
    import socket
    ip = socket.gethostbyname(RTMP_HOST)
    print(f"✅ DNS 解析成功: {RTMP_HOST} -> {ip}")
except Exception as e:
    print(f"❌ DNS 解析失败: {e}")

# ========== 总结 ==========
print("\n" + "=" * 60)
print("测试总结")
print("=" * 60)

tests = [
    ("UDP 连接", udp_ok),
    ("RTMP 连接", rtmp_ok),
    ("模块功能", module_ok),
]

all_ok = True
for name, status in tests:
    symbol = "✅" if status else "❌"
    print(f"{symbol} {name}: {'通过' if status else '失败'}")
    if not status:
        all_ok = False

print("=" * 60)

if all_ok:
    print("\n🎉 所有测试通过！可以正常对接甲方B")
    print("\n下一步：")
    print("1. 运行主程序: python main.py --preset client_b")
    print("2. 访问管理平台验证推流:")
    print("   https://www.xsjny.com/web/robot-analysis-ui/index.html")
    print("   账号密码见本地 config/platform_accounts.local.json")
else:
    print("\n⚠️  部分测试失败，请检查：")
    print("1. 网络连接是否正常")
    print("2. 服务器地址和端口是否正确")
    print("3. 防火墙是否阻止了连接")
    print("4. 服务器是否正在运行")

print("\n" + "=" * 60)
