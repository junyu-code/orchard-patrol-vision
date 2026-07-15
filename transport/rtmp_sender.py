import subprocess


def _display_rtmp_url(url):
    """隐藏 RTMP 查询参数，避免签名进入控制台和日志。"""
    base_url, separator, _ = str(url or "").partition("?")
    return f"{base_url}?<redacted>" if separator else base_url


class RtmpSender:
    """RTMP推流类：通过FFmpeg将OpenCV图像推送到RTMP服务器"""
    
    def __init__(
        self,
        rtmp_url="",
        video_bitrate="700k",
        maxrate="900k",
        bufsize="1400k",
        preset="veryfast",
    ):
        self.rtmp_url = rtmp_url
        self.video_bitrate = video_bitrate
        self.maxrate = maxrate
        self.bufsize = bufsize
        self.preset = preset
        self.process = None
        self.is_running = False
        
    def start(self, width, height, fps=25):
        """
        启动FFmpeg推流进程
        :param width: 视频宽度
        :param height: 视频高度
        :param fps: 帧率
        """
        if not self.rtmp_url:
            print("错误: 未配置 RTMP 推流地址")
            return False
        if self.is_running:
            return
            
        # 根据操作系统选择ffmpeg命令路径，通常假设ffmpeg在环境变量中
        ffmpeg_cmd = 'ffmpeg'
        
        # 构建FFmpeg命令
        # -f rawvideo: 输入原始视频数据
        # -vcodec rawvideo: 输入编码格式
        # -s WxH: 分辨率
        # -pix_fmt bgr24: 这里声明的是“输入格式”，因为OpenCV传给FFmpeg的原始帧是BGR三通道
        # 注意：yuv420p通常是“输出编码格式”，需要放在libx264后面；两者位置和含义不同
        # -r fps: 帧率
        # -i -: 从标准输入(stdin)读取数据
        # -an: 无音频
        # -vcodec libx264: 使用H.264编码
        # -preset: 编码速度和压缩效率的平衡，甲方B低带宽场景默认使用 veryfast
        # -tune zerolatency: 零延迟调优
        # -b:v/-maxrate/-bufsize: 控制码率，避免测试服务器入口积压
        # -f flv: 输出格式为FLV (RTMP标准封装)
        # -loglevel error: 只显示错误信息，隐藏 info/debug 日志，防止刷屏
        command = [
            ffmpeg_cmd,
            '-y',
            '-loglevel', 'error',  # <--- 关键修改：设置日志级别为 error
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-s', f'{width}x{height}',
            '-pix_fmt', 'bgr24',
            '-r', str(fps),
            '-i', '-',
            '-an',
            '-vcodec', 'libx264',
            '-preset', self.preset,
            '-tune', 'zerolatency',
            '-pix_fmt', 'yuv420p',
            '-b:v', self.video_bitrate,
            '-maxrate', self.maxrate,
            '-bufsize', self.bufsize,
            '-g', str(max(1, int(fps) * 2)),
            '-f', 'flv',
            self.rtmp_url
        ]
        
        try:
            # 启动子进程
            # stdout=subprocess.DEVNULL: 丢弃标准输出（通常是进度条统计信息）
            # stderr=subprocess.PIPE: 保留标准错误（通常是报错信息），以便在控制台看到
            # 注意：如果希望连报错也完全隐藏，可以将 stderr 也改为 subprocess.DEVNULL
            self.process = subprocess.Popen(
                command, 
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.PIPE 
            )
            self.is_running = True
            print(
                f"RTMP推流已启动: {_display_rtmp_url(self.rtmp_url)} "
                f"({width}x{height}@{fps}fps, {self.video_bitrate})"
            )
        except FileNotFoundError:
            print("错误: 未找到 FFmpeg。请确保 FFmpeg 已安装并添加到系统环境变量 PATH 中。")
            self.is_running = False
        except Exception as e:
            print(f"RTMP推流启动失败: {e}")
            self.is_running = False

    def send_frame(self, frame):
        """
        发送一帧图像到FFmpeg
        :param frame: OpenCV格式的numpy数组 (BGR)
        """
        if not self.is_running or self.process is None:
            return False
        
        try:
            # 将图像数据写入FFmpeg的stdin
            self.process.stdin.write(frame.tobytes())
            return True
        except BrokenPipeError:
            print("RTMP连接断开 (BrokenPipe)")
            self.stop()
            return False
        except Exception as e:
            print(f"RTMP发送帧失败: {e}")
            self.stop()
            return False

    def stop(self):
        """停止推流并关闭FFmpeg进程"""
        if self.process:
            try:
                if self.process.stdin:
                    self.process.stdin.close()
                self.process.wait(timeout=5) # 等待进程结束
            except subprocess.TimeoutExpired:
                self.process.kill() # 超时则强制杀死
            except Exception as e:
                print(f"关闭FFmpeg进程时出错: {e}")
            finally:
                self.process = None
                self.is_running = False
                print("RTMP推流已停止")

    def __del__(self):
        self.stop()
