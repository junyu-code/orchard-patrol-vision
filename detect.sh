#!/bin/bash

# ================= 配置区域 =================
# 1. 项目根目录 (注意空格转义或加引号)，这里因为文件名带空格的原因，用了软链接
PROJECT_DIR="/home/rm/yolo_detect"

# 2. Conda 环境中 Python 的绝对路径 (关键！)
# 请根据 'which python' 的实际输出修改这里
PYTHON_BIN="/home/rm/miniconda3/envs/detect/bin/python"

# 3. 主程序文件名
MAIN_SCRIPT="main.py"

# 4. 日志配置
LOG_DIR="${PROJECT_DIR}/logs"
LOG_PREFIX="detect_run"
# ===========================================

# --- 脚本开始 ---

# 1. 进入项目目录
cd "${PROJECT_DIR}" || { echo "Error: Cannot enter project directory"; exit 1; }

# 2. 创建日志目录
mkdir -p "${LOG_DIR}"

# 3. 生成带时间戳的日志文件名
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
LOG_FILE="${LOG_DIR}/${LOG_PREFIX}_${TIMESTAMP}.log"

# 4. 【核心功能】清理2天前的旧日志
# 查找 logs 目录下以 detect_run_ 开头且修改时间超过2天的文件并删除
find "${LOG_DIR}" -name "${LOG_PREFIX}_*.log" -type f -mtime +2 -exec rm -f {} \;
echo "[$(date)] 系统启动: 已自动清理2天前的旧日志" >> "${LOG_FILE}"

# 5. 设置必要的环境变量
# PyQt5 需要知道显示在哪里
export DISPLAY=:0
# 强制使用 XCB 平台插件，避免 Wayland 冲突
export QT_QPA_PLATFORM=xcb
# 如果有其他库路径问题，可以在这里添加 LD_LIBRARY_PATH

# 6. 启动程序
echo "[$(date)] 正在使用环境: ${PYTHON_BIN} 启动程序..." >> "${LOG_FILE}"

# nohup: 后台运行，即使终端关闭也不停止
# & : 放入后台
# >> "${LOG_FILE}" 2>&1 : 将标准输出和错误输出都追加到日志文件
nohup "${PYTHON_BIN}" "${MAIN_SCRIPT}" >> "${LOG_FILE}" 2>&1 &

# 7. 记录进程 ID (PID)，方便后续手动停止
echo $! > "${PROJECT_DIR}/detect.pid"
echo "[$(date)] 程序已启动，PID: $!" >> "${LOG_FILE}"
echo "[$(date)] 日志文件位置: ${LOG_FILE}" >> "${LOG_FILE}"