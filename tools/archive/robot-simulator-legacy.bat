@echo off
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "PYTHON_PATH=D:\Anaconda3\envs\yolov5_pyqt5\python.exe"
if not exist "%PYTHON_PATH%" set "PYTHON_PATH=python"

set "DEFAULT_SOURCE_VIDEO=%SCRIPT_DIR%..\videos\test0.mp4"
set "DEFAULT_VIDEO_FILE=%SCRIPT_DIR%..\videos\test0_pingpong.mp4"
set "DEFAULT_ROBOT_ID=1"
set "DEFAULT_ROBOT_STATUS=1"
set "DEFAULT_SENSOR_ID=1"
set "DEFAULT_ORCHARD_ID=orchard1"
set "PLATFORM_UDP_HOST=1.15.149.164"
set "PLATFORM_UDP_PORT=4926"
set "PLATFORM_RTMP_HOST=www.xsjny.com"
set "LEGACY_UDP_HOST=43.139.69.203"
set "LEGACY_UDP_PORT=10088"
set "LEGACY_RTMP_HOST=43.139.69.203"
set "LEGACY_RTMP_PORT=1936"
set "RTSP_PORT=8554"
set "TREE_INTERVAL=8"
set "TREE_JITTER=2"

"%PYTHON_PATH%" --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found: %PYTHON_PATH%
    pause
    exit /b 1
)

ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] ffmpeg not found. Please install ffmpeg and add it to PATH.
    pause
    exit /b 1
)

:config_menu
cls
echo ========================================
echo     Robot Push Simulator
echo     Video Stream + UDP Data
echo ========================================
echo.

echo 1. Endpoint preset:
echo    [1] platform  UDP 1.15.149.164:4926, RTMP www.xsjny.com
echo    [2] legacy    UDP 43.139.69.203:10088, RTMP 43.139.69.203:1936
set /p "endpoint_choice=Choose endpoint (1-2, default=1): "
if "%endpoint_choice%"=="" set "endpoint_choice=1"
if "%endpoint_choice%"=="2" (
    set "ENDPOINT=legacy"
    set "DEFAULT_UDP_HOST=%LEGACY_UDP_HOST%"
    set "UDP_PORT=%LEGACY_UDP_PORT%"
    set "DEFAULT_RTMP_HOST=%LEGACY_RTMP_HOST%"
    set "RTMP_PORT=%LEGACY_RTMP_PORT%"
) else (
    set "ENDPOINT=platform"
    set "DEFAULT_UDP_HOST=%PLATFORM_UDP_HOST%"
    set "UDP_PORT=%PLATFORM_UDP_PORT%"
    set "DEFAULT_RTMP_HOST=%PLATFORM_RTMP_HOST%"
    set "RTMP_PORT="
)
echo.

echo 2. Orchard:
echo    [1] orchard1
echo    [2] orchard2
echo    [3] custom
set /p "orchard_choice=Choose orchard (1-3, default=1): "
if "%orchard_choice%"=="" set "orchard_choice=1"
if "%orchard_choice%"=="1" (
    set "ORCHARD_ID=orchard1"
) else if "%orchard_choice%"=="2" (
    set "ORCHARD_ID=orchard2"
) else if "%orchard_choice%"=="3" (
    set /p "ORCHARD_ID=Input orchard id: "
    if "!ORCHARD_ID!"=="" set "ORCHARD_ID=%DEFAULT_ORCHARD_ID%"
) else (
    set "ORCHARD_ID=orchard1"
)
echo.

echo 3. Robot:
echo    [1] robot1
echo    [2] robot2
echo    [3] robot3
set /p "robot_choice=Choose robot (1-3, default=1): "
if "%robot_choice%"=="" set "robot_choice=1"
if "%robot_choice%"=="1" (
    set "ROBOT_ID=1"
    set "ROBOT_NAME=robot1"
) else if "%robot_choice%"=="2" (
    set "ROBOT_ID=2"
    set "ROBOT_NAME=robot2"
) else if "%robot_choice%"=="3" (
    set "ROBOT_ID=3"
    set "ROBOT_NAME=robot3"
) else (
    set "ROBOT_ID=1"
    set "ROBOT_NAME=robot1"
)
set "ROBOT_STATUS=%DEFAULT_ROBOT_STATUS%"
echo.

echo 4. Sensor:
echo    [1] sensor1
echo    [2] sensor2
set /p "sensor_choice=Choose sensor (1-2, default=1): "
if "%sensor_choice%"=="" set "sensor_choice=1"
if "%sensor_choice%"=="1" (
    set "SENSOR_ID=1"
    set "SENSOR_NAME=sensor1"
) else if "%sensor_choice%"=="2" (
    set "SENSOR_ID=2"
    set "SENSOR_NAME=sensor2"
) else (
    set "SENSOR_ID=1"
    set "SENSOR_NAME=sensor1"
)
echo.

set /p "UDP_HOST=UDP host (default=%DEFAULT_UDP_HOST%): "
if "%UDP_HOST%"=="" set "UDP_HOST=%DEFAULT_UDP_HOST%"
echo.

set /p "RTMP_HOST=RTMP host (default=%DEFAULT_RTMP_HOST%): "
if "%RTMP_HOST%"=="" set "RTMP_HOST=%DEFAULT_RTMP_HOST%"
echo.

set /p "START_VIDEO=Start local default video? (Y/n): "
if /i "%START_VIDEO%"=="n" (
    set "START_VIDEO=0"
) else (
    set "START_VIDEO=1"
)

if "%START_VIDEO%"=="1" (
    set /p "VIDEO_FILE=Video file (default=%DEFAULT_VIDEO_FILE%): "
    if "!VIDEO_FILE!"=="" set "VIDEO_FILE=%DEFAULT_VIDEO_FILE%"
    if not exist "!VIDEO_FILE!" (
        echo [ERROR] Video file not found: !VIDEO_FILE!
        pause
        goto config_menu
    )
)
echo.

cls
echo ========================================
echo     Confirm Configuration
echo ========================================
echo Orchard:      %ORCHARD_ID%
echo Endpoint:     %ENDPOINT%
echo Robot:        %ROBOT_ID% (%ROBOT_NAME%)
echo Robot status: %ROBOT_STATUS%
echo Sensor:       %SENSOR_ID% (%SENSOR_NAME%)
echo UDP host:     %UDP_HOST%
echo UDP port:     %UDP_PORT%
echo RTMP host:    %RTMP_HOST%
echo Tree interval:%TREE_INTERVAL% +/- %TREE_JITTER% frames
if "%START_VIDEO%"=="1" (
    echo Video:        enabled
    echo Video file:   %VIDEO_FILE%
) else (
    echo Video:        disabled
)
echo.
echo RTMP URL:
if "%ENDPOINT%"=="legacy" (
    echo rtmp://%RTMP_HOST%:%RTMP_PORT%/live/%ORCHARD_ID%_%ROBOT_NAME%_%SENSOR_NAME%
) else (
    echo rtmp://%RTMP_HOST%/live/%ROBOT_NAME%_%SENSOR_NAME%
)
echo.
set /p "confirm=Start streaming? (Y/n): "
if /i "%confirm%"=="n" goto config_menu

if "%ENDPOINT%"=="legacy" (
    set "STREAM_URL=rtmp://%RTMP_HOST%:%RTMP_PORT%/live/%ORCHARD_ID%_%ROBOT_NAME%_%SENSOR_NAME%"
) else (
    set "STREAM_URL=rtmp://%RTMP_HOST%/live/%ROBOT_NAME%_%SENSOR_NAME%"
)
set "STREAM_TRANSPORT=rtmp"

cls
echo ========================================
echo     Starting Robot Push Simulator
echo ========================================
echo.
echo [1/2] Starting UDP simulator...
start "UDP Simulator - %ROBOT_NAME%-%SENSOR_NAME%" "%PYTHON_PATH%" "%SCRIPT_DIR%SimulateUDP.py" %ROBOT_ID% %ROBOT_STATUS% %UDP_HOST% %UDP_PORT% 0 1.0 %TREE_INTERVAL% %TREE_JITTER%

timeout /t 2 /nobreak >nul

if "%START_VIDEO%"=="0" (
    echo Video stream disabled. UDP simulator is running.
    echo Close the UDP simulator window to stop.
    pause
    endlocal
    exit /b 0
)

echo [2/2] Starting video stream...
echo Stream URL: %STREAM_URL%
echo.
echo Press Ctrl+C to stop video streaming.
echo Close the UDP simulator window manually after stopping.
echo.

ffmpeg -re -stream_loop -1 -i "%VIDEO_FILE%" ^
  -vf "scale=640:-2,fps=15" ^
  -c:v libx264 -preset veryfast -tune zerolatency ^
  -b:v 700k -maxrate 900k -bufsize 1400k -g 30 ^
  -an ^
  -f flv ^
  "%STREAM_URL%"

echo.
echo Stream stopped.
pause
endlocal
