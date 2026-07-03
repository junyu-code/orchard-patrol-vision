#!/usr/bin/env python3
"""
公开版 UDP 协议测试发送器。

用途：
1. 给接收方独立测试 UDP 解析逻辑。
2. 不依赖本项目业务代码，不包含甲方业务地址和推流逻辑。
3. 默认发送 orchard1| + 28 字节机器人协议包，格式与转发服务一致。
"""

import argparse
import socket
import time
from datetime import datetime


HEAD = 0x66
TAIL = 0x99
LAT_NORTH = 0x4E
LAT_SOUTH = 0x53
LON_EAST = 0x45
LON_WEST = 0x57


def clamp(value, low, high):
    """把数值限制在协议允许范围内。"""
    return int(max(low, min(high, value)))


def decimal_to_dms(decimal_value, is_latitude=True):
    """十进制度转协议使用的度、分、秒、方向。"""
    direction = LAT_NORTH if is_latitude else LON_EAST
    if decimal_value < 0:
        direction = LAT_SOUTH if is_latitude else LON_WEST

    total_seconds = int(round(abs(float(decimal_value)) * 3600))
    degree = total_seconds // 3600
    minute = (total_seconds % 3600) // 60
    second = total_seconds % 60
    return degree, minute, second, direction


def pack_robot_data(
    robot_id,
    robot_status,
    frame_index,
    left_tree_code,
    right_tree_code,
    latitude,
    longitude,
    azimuth,
    velocity,
    eye_point_height,
    bat_voltage,
    soc,
):
    """打包 28 字节机器人 UDP 协议包。"""
    now = datetime.now()
    lat_degree, lat_minute, lat_second, lat_direction = decimal_to_dms(latitude, True)
    lon_degree, lon_minute, lon_second, lon_direction = decimal_to_dms(longitude, False)

    robot_id = clamp(robot_id, 0, 255)
    robot_status = clamp(robot_status, 0, 255)
    frame_index = clamp(frame_index, 0, 65535)
    left_tree_code = clamp(left_tree_code, 0, 65535)
    right_tree_code = clamp(right_tree_code, 0, 65535)
    lat_degree = clamp(lat_degree, 0, 90)
    lat_minute = clamp(lat_minute, 0, 59)
    lat_second = clamp(lat_second, 0, 59)
    lon_degree = clamp(lon_degree, 0, 180)
    lon_minute = clamp(lon_minute, 0, 59)
    lon_second = clamp(lon_second, 0, 59)
    azimuth = clamp(azimuth, 0, 65535)
    velocity = clamp(velocity, 0, 255)
    eye_point_height = clamp(eye_point_height, 0, 255)
    bat_voltage = clamp(bat_voltage, 0, 255)
    soc = clamp(soc, 0, 100)

    data_bytes = [
        robot_id,
        robot_status,
        (frame_index >> 8) & 0xFF,
        frame_index & 0xFF,
        (left_tree_code >> 8) & 0xFF,
        left_tree_code & 0xFF,
        (right_tree_code >> 8) & 0xFF,
        right_tree_code & 0xFF,
        clamp(now.hour, 0, 23),
        clamp(now.minute, 0, 59),
        clamp(now.second, 0, 59),
        lat_degree,
        lat_minute,
        lat_second,
        lat_direction,
        lon_degree,
        lon_minute,
        lon_second,
        lon_direction,
        (azimuth >> 8) & 0xFF,
        azimuth & 0xFF,
        velocity,
        eye_point_height,
        bat_voltage,
        soc,
    ]
    checksum = sum(data_bytes) & 0xFF
    return bytes([HEAD] + data_bytes + [checksum, TAIL])


def build_packet(args, frame_index):
    """根据命令行参数生成最终 UDP 数据。"""
    left_tree_code = args.left_tree_code
    right_tree_code = args.right_tree_code
    if args.increment_tree:
        left_tree_code += (frame_index - 1) * 2
        right_tree_code += (frame_index - 1) * 2

    raw_packet = pack_robot_data(
        robot_id=args.robot_id,
        robot_status=args.robot_status,
        frame_index=frame_index,
        left_tree_code=left_tree_code,
        right_tree_code=right_tree_code,
        latitude=args.latitude,
        longitude=args.longitude,
        azimuth=args.azimuth,
        velocity=args.velocity,
        eye_point_height=args.eye_point_height,
        bat_voltage=args.bat_voltage,
        soc=args.soc,
    )

    if args.no_prefix:
        return raw_packet, left_tree_code, right_tree_code

    prefix = f"{args.orchard_code}|".encode("utf-8")
    return prefix + raw_packet, left_tree_code, right_tree_code


def parse_args():
    parser = argparse.ArgumentParser(
        description="公开版 UDP 协议测试发送器，默认发送 orchard1| + 28 字节机器人数据包。"
    )
    parser.add_argument("--host", default="127.0.0.1", help="接收方 UDP 地址")
    parser.add_argument("--port", type=int, default=5006, help="接收方 UDP 端口")
    parser.add_argument("--count", type=int, default=10, help="发送次数，0 表示一直发送")
    parser.add_argument("--interval", type=float, default=1.0, help="发送间隔，单位秒")
    parser.add_argument("--orchard-code", default="orchard1", help="果园编号前缀")
    parser.add_argument("--no-prefix", action="store_true", help="只发送裸 28 字节协议包")
    parser.add_argument("--robot-id", type=int, default=1, help="机器人编号")
    parser.add_argument("--robot-status", type=int, default=1, help="机器人状态，0=移动，1=靠近树/拍照")
    parser.add_argument("--left-tree-code", type=int, default=35, help="左侧果树编号")
    parser.add_argument("--right-tree-code", type=int, default=36, help="右侧果树编号")
    parser.add_argument("--increment-tree", action="store_true", help="每次发送后左右果树编号自动递增")
    parser.add_argument("--latitude", type=float, default=25.28, help="纬度，默认 25.28")
    parser.add_argument("--longitude", type=float, default=110.34, help="经度，默认 110.34")
    parser.add_argument("--azimuth", type=int, default=14, help="方位角，单位度")
    parser.add_argument("--velocity", type=int, default=6, help="速度协议值，1LSB=0.1m/s")
    parser.add_argument("--eye-point-height", type=int, default=157, help="相机高度协议值，1LSB=0.01m")
    parser.add_argument("--bat-voltage", type=int, default=240, help="电池电压协议值，1LSB=0.1V")
    parser.add_argument("--soc", type=int, default=98, help="电量百分比")
    return parser.parse_args()


def main():
    args = parse_args()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    frame_index = 1

    print("UDP 协议测试发送器已启动")
    print(f"目标地址: {args.host}:{args.port}")
    print(f"GPS: latitude={args.latitude}, longitude={args.longitude}")
    print(f"发送格式: {'裸 28 字节协议包' if args.no_prefix else args.orchard_code + '| + 28 字节协议包'}")

    try:
        while args.count == 0 or frame_index <= args.count:
            packet, left_tree_code, right_tree_code = build_packet(args, frame_index)
            sock.sendto(packet, (args.host, args.port))
            print(
                f"已发送 #{frame_index} | {len(packet)} 字节 | "
                f"leftTreeCode={left_tree_code}, rightTreeCode={right_tree_code} | "
                f"hex={packet.hex(' ')}"
            )
            frame_index += 1
            time.sleep(max(0.0, args.interval))
    except KeyboardInterrupt:
        print("已停止发送")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
