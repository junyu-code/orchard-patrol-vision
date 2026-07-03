@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_DIR=%%~fI"
set "PYTHON_PATH=D:\Anaconda3\envs\yolov5_pyqt5\python.exe"
if not exist "%PYTHON_PATH%" set "PYTHON_PATH=python"

set "VIDEO_FILE=%PROJECT_DIR%\samples\videos\robot_push\test0_push.mp4"
set "RTMP_URL=rtmp://www.xsjny.com/live/robot1_sensor1"
set "UDP_TARGET=1.15.149.164:4926"

cls
echo.
echo ============================================================
echo   orchard-patrol-vision - Client B Demo
echo ============================================================
echo   Mode      : RTMP video stream + UDP robot telemetry
echo   Video     : %VIDEO_FILE%
echo   RTMP URL  : %RTMP_URL%
echo   UDP target: %UDP_TARGET%
echo ------------------------------------------------------------
echo   UDP packet fields
echo   robot id / status / frame / left-right tree id / time
echo   GPS / azimuth / speed / camera height / voltage / battery
echo ------------------------------------------------------------
echo   Tree detection simulation
echo   built-in patrol timeline, written into UDP tree id fields only
echo   Tree ID starts from ID0001 and increases at each event
echo ------------------------------------------------------------
echo   Console prints UDP heartbeat summaries and tree events.
echo   Press Ctrl+C to stop.
echo ============================================================
echo.

pushd "%PROJECT_DIR%" >nul
"%PYTHON_PATH%" "%PROJECT_DIR%\main.py" --preset client_b --source "%VIDEO_FILE%" --auto-start
popd >nul

endlocal
