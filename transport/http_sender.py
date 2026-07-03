import requests
import json
import threading
import base64
import cv2 # 用于图片编码

class HttpSender:
    """
    机器人主动上报客户端（POST版）
    包含 GPS 和 图像帧 (Base64)
    """

    def __init__(self, push_url="https://webhook.site/b1765265-19e1-4854-994d-62f0e85f2807"):
        self.push_url = push_url  
        self.headers = {
            "Content-Type": "application/json; charset=utf-8"
        }

    def start_server(self):
        print(f"✅ HTTP 主动上报模式已初始化，目标地址: {self.push_url}")
        pass

    def send_robot_with_disease(
        self,
        robot_id, 
        robot_status, 
        frame_index,
        route_index,
        waypoint_index,
        tree_index,
        azimuth, 
        velocity, 
        eyepoint_height, 
        bat_voltage, 
        state_of_charge,
        conf1, count1, 
        conf2, count2, 
        conf3, count3,
        lat_degree=0, lat_minute=0, lat_second=0, lat_direction="N",
        lon_degree=0, lon_minute=0, lon_second=0, lon_direction="E",
        image_frame=None  # 传入 cv2 的 numpy 数组 (BGR)
    ):
        
        # --- 图片转 Base64 (可选) ---
        img_base64 = ""
        if image_frame is not None:
            try:
                # cv2.imencode 将图片转为 jpg 字节流，质量设为 70 以减小体积
                _, encoded_img = cv2.imencode('.jpg', image_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                # 转为 base64 字符串
                img_base64 = base64.b64encode(encoded_img).decode('utf-8')
                
                # 【新增】调试用：将图片保存为本地文件，方便直接查看
                # import time
                # debug_filename = f"debug_frame_{int(time.time())}.jpg"
                # with open(debug_filename, 'wb') as f:
                #     f.write(encoded_img.tobytes())
                # print(f"💾 调试图片已保存: {debug_filename}")
                
            except Exception as e:
                print(f"⚠️ 图片编码失败: {e}")

        # 构造标准JSON
        data = {
            # 机器人ID
            "ID": robot_id,
            # 机器人状态
            "Status": robot_status,
            # 数据帧
            "Frame": frame_index,
            # 作业路线编号
            "Route": route_index,
            # 作业路径点
            "Waypoint": waypoint_index,
            # 果树编号
            "Tree": tree_index,
            # GPS数据
            "GPS": {
                # 纬度
                "Lat": {
                    # 度
                    "Degree": lat_degree,
                    # 分
                    "Minute": lat_minute,
                    # 秒
                    "Second": lat_second,
                    # 方向
                    "Direction": lat_direction
                },
                # 经度
                "Lon": {
                    "Degree": lon_degree,
                    "Minute": lon_minute,
                    "Second": lon_second,
                    "Direction": lon_direction
                }
            },
            # 机器人行进方向
            "Azimuth": azimuth,
            # 机器人前向行进速度
            "Velocity": velocity,
            # 摄像机视点相对高度
            "Height": eyepoint_height,
            # 机器人电池电压值
            "BATVoltage": bat_voltage,
            # 剩余电量百分比
            "SOC": state_of_charge,
            # 检测图像数据
            "Image": img_base64,
            # 检测结果
            "Diseases": [
                {"conf": conf1, "count": count1}, # Index 0: Canker 溃疡病
                {"conf": conf2, "count": count2}, # Index 1: Huanglongbing 黄龙病
                {"conf": conf3, "count": count3}  # Index 2: Anthracnose 炭疽病
            ]
        }

        # 后台线程发送
        def post_task():
            try:
                response = requests.post(
                    self.push_url,
                    data=json.dumps(data, ensure_ascii=False),
                    headers=self.headers,
                    timeout=5 # 图片较大，适当增加超时时间
                )
                if response.status_code == 200:
                    pass
                else:
                    print(f"❌ 上报失败 | 状态码:{response.status_code}")
            except Exception as e:
                print(f"⚠️ 上报异常: {e}")

        threading.Thread(target=post_task, daemon=True).start()

    def stop(self):
        pass