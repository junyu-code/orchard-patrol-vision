import cv2
import glob
import sys
import os


class Camera:
    def __init__(self, cam_preset_num=5):
        self.cam_preset_num = cam_preset_num

    def get_cam_num(self):
        cnt = 0
        devices = []
        if sys.platform.startswith("linux"):
            paths = sorted(
                glob.glob("/dev/video*"),
                key=lambda path: int(path.rsplit("video", 1)[-1]),
            )
            # 一个 USB 摄像头通常会暴露 videoN 和 videoN+1 两个节点，
            # 通过 sysfs 的物理设备路径去重，只保留编号较小的主节点。
            physical_devices = {}
            for path in paths:
                number = int(path.rsplit("video", 1)[-1])
                sysfs_device = os.path.realpath(f"/sys/class/video4linux/video{number}/device")
                physical_devices.setdefault(sysfs_device, number)
            candidates = sorted(physical_devices.values())
            candidates = candidates or list(range(self.cam_preset_num))
            backend = getattr(cv2, "CAP_V4L2", 0)
        elif sys.platform.startswith("win"):
            candidates = list(range(self.cam_preset_num))
            backend = getattr(cv2, "CAP_DSHOW", 0)
        else:
            candidates = list(range(self.cam_preset_num))
            backend = 0
        for device in candidates:
            stream = cv2.VideoCapture(device, backend) if backend else cv2.VideoCapture(device)
            try:
                # isOpened is more reliable than a single grab during camera warm-up.
                available = stream.isOpened()
                if not available:
                    # 节点存在但被本程序或其他进程占用时，仍然是有效的物理摄像头。
                    if sys.platform.startswith("linux") and os.path.exists(f"/dev/video{device}"):
                        cnt += 1
                        devices.append(device)
                    continue
                grabbed = stream.grab()
                if not grabbed:
                    grabbed = stream.read()[0]
                if available or grabbed:
                    cnt += 1
                    devices.append(device)
            finally:
                stream.release()
        return cnt, devices


if __name__ == '__main__':
    cam = Camera()
    cam_num, devices = cam.get_cam_num()
    print(cam_num, devices)
