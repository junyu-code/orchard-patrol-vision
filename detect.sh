#!/bin/bash

if [ "$(uname -s)" != "Linux" ]; then
    echo "detect.sh 仅用于 Linux 部署；Windows 请直接运行 python main.py"
    exit 2
fi

# ================= 配置区域 =================
# 1. 项目根目录：默认使用本脚本所在目录，避免仓库改名或移动后仍指向旧路径
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 2. Conda 环境中 Python 的绝对路径 (关键！)
# 请根据 'which python' 的实际输出修改这里
PYTHON_BIN="/home/rm/miniconda3/envs/detect/bin/python"

# 3. 主程序文件名
MAIN_SCRIPT="main.py"
RUN_FOREGROUND=false
if [ "${1:-}" = "--foreground" ]; then
    RUN_FOREGROUND=true
    shift
fi
# 当前 USB 转串口设备由 udev 映射为 ttyGPS_IN；保留环境变量覆盖入口。
TELEMETRY_SERIAL_PORT="${TELEMETRY_SERIAL_PORT:-/dev/ttyGPS_IN}"
TELEMETRY_SERIAL_BAUDRATE="${TELEMETRY_SERIAL_BAUDRATE:-9600}"
DATA_MODE="${DATA_MODE:-debug}"
APP_PRESET="${APP_PRESET:-client_b}"
MAIN_ARGS=(
    --preset "${APP_PRESET}"
    --data-mode "${DATA_MODE}"
    --source 0
    --auto-start
    --enable-telemetry-serial
    --telemetry-port "${TELEMETRY_SERIAL_PORT}"
    --telemetry-baudrate "${TELEMETRY_SERIAL_BAUDRATE}"
    --no-telemetry-auto-detect
)

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

# 5. 避免 systemd 和桌面自启动同时触发时重复启动
is_running_main() {
    local pid="$1"
    local cwd=""
    local cmd=""

    if [ -z "${pid}" ] || ! kill -0 "${pid}" 2>/dev/null; then
        return 1
    fi

    cwd=$(readlink -f "/proc/${pid}/cwd" 2>/dev/null || true)
    cmd=$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null || true)

    [ "${cwd}" = "${PROJECT_DIR}" ] && echo "${cmd}" | grep -q "${MAIN_SCRIPT}"
}

find_running_main_pid() {
    local old_pid=""
    local pid=""

    if [ -f "${PROJECT_DIR}/detect.pid" ]; then
        old_pid=$(cat "${PROJECT_DIR}/detect.pid" 2>/dev/null)
        if is_running_main "${old_pid}"; then
            echo "${old_pid}"
            return 0
        fi
    fi

    for pid in $(pgrep -f "python.*${MAIN_SCRIPT}" 2>/dev/null || true); do
        if [ "${pid}" != "$$" ] && is_running_main "${pid}"; then
            echo "${pid}"
            return 0
        fi
    done

    return 1
}

RUNNING_PID=$(find_running_main_pid)
if [ -n "${RUNNING_PID}" ]; then
    echo "${RUNNING_PID}" > "${PROJECT_DIR}/detect.pid"
    echo "[$(date)] 程序已在运行，PID: ${RUNNING_PID}" >> "${LOG_FILE}"
    exit 0
fi

# 6. 设置必要的环境变量
# PyQt5 需要知道显示在哪里
export DISPLAY=:0
# 强制使用 XCB 平台插件，避免 Wayland 冲突
export QT_QPA_PLATFORM=xcb
# 让 nohup 日志实时落盘，便于现场确认遥测串口打开和解析状态
export PYTHONUNBUFFERED=1
# 如果有其他库路径问题，可以在这里添加 LD_LIBRARY_PATH

# 7. 启动程序
echo "[$(date)] 正在使用环境: ${PYTHON_BIN} 启动程序..." >> "${LOG_FILE}"
echo "[$(date)] 业务预设: ${APP_PRESET}" >> "${LOG_FILE}"
echo "[$(date)] 电控遥测串口: ${TELEMETRY_SERIAL_PORT} @ ${TELEMETRY_SERIAL_BAUDRATE}" >> "${LOG_FILE}"
echo "[$(date)] 数据模式: ${DATA_MODE}" >> "${LOG_FILE}"

if [ "${RUN_FOREGROUND}" = true ]; then
    # systemd 必须直接管理 Python 进程，exec 可避免遗留孤立的 nohup 进程。
    echo $$ > "${PROJECT_DIR}/detect.pid"
    echo "[$(date)] systemd 前台模式启动，PID: $$" >> "${LOG_FILE}"
    echo "[$(date)] 日志文件位置: ${LOG_FILE}" >> "${LOG_FILE}"
    exec "${PYTHON_BIN}" -u "${MAIN_SCRIPT}" "${MAIN_ARGS[@]}" >> "${LOG_FILE}" 2>&1
fi

# 桌面自启动立即返回，GUI 在后台继续运行。
nohup "${PYTHON_BIN}" -u "${MAIN_SCRIPT}" "${MAIN_ARGS[@]}" >> "${LOG_FILE}" 2>&1 &

# 8. 记录进程 ID (PID)，方便后续手动停止
echo $! > "${PROJECT_DIR}/detect.pid"
echo "[$(date)] 桌面后台模式启动，PID: $!" >> "${LOG_FILE}"
echo "[$(date)] 日志文件位置: ${LOG_FILE}" >> "${LOG_FILE}"
