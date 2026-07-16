@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "VIDEO_FILE=%SCRIPT_DIR%..\samples\videos\robot_push\test_demo.mp4"
set "ROBOT_ID=robot1"
set "SENSOR_ID=sensor1"
set "ORCHARD_ID=orchard1"
set "RTSP_SERVER=www.xsjny.com"
set "RTMP_SERVER=gl.xsjny.com"
set "RTSP_PORT=8554"

echo ========================================
echo     Video Push Test
echo ========================================
echo Video:  %VIDEO_FILE%
echo RTSP:   rtsp://%RTSP_SERVER%:%RTSP_PORT%/live/%ORCHARD_ID%/%ROBOT_ID%/%SENSOR_ID%
echo RTMP:   rtmp://%RTMP_SERVER%/live/%ROBOT_ID%_%SENSOR_ID%
echo.

:menu
echo Choose push mode:
echo   [1] RTSP + TCP
echo   [2] RTSP + UDP
echo   [3] RTMP
echo   [4] Exit
echo.
set /p "choice=Input choice (1-4): "

if "%choice%"=="1" goto rtsp_tcp
if "%choice%"=="2" goto rtsp_udp
if "%choice%"=="3" goto rtmp
if "%choice%"=="4" goto end
goto menu

:rtsp_tcp
ffmpeg -re -i "%VIDEO_FILE%" ^
  -vf "scale=640:-2,fps=15" ^
  -c:v libx264 -preset veryfast -tune zerolatency ^
  -b:v 700k -maxrate 900k -bufsize 1400k -g 30 ^
  -an ^
  -rtsp_transport tcp ^
  -f rtsp ^
  "rtsp://%RTSP_SERVER%:%RTSP_PORT%/live/%ORCHARD_ID%/%ROBOT_ID%/%SENSOR_ID%"
goto end

:rtsp_udp
ffmpeg -re -i "%VIDEO_FILE%" ^
  -vf "scale=640:-2,fps=15" ^
  -c:v libx264 -preset veryfast -tune zerolatency ^
  -b:v 700k -maxrate 900k -bufsize 1400k -g 30 ^
  -an ^
  -rtsp_transport udp ^
  -f rtsp ^
  "rtsp://%RTSP_SERVER%:%RTSP_PORT%/live/%ORCHARD_ID%/%ROBOT_ID%/%SENSOR_ID%"
goto end

:rtmp
ffmpeg -re -i "%VIDEO_FILE%" ^
  -vf "scale=1280:-2,fps=30" ^
  -c:v libx264 -preset veryfast -tune zerolatency ^
  -b:v 3000k -maxrate 3600k -bufsize 6000k -g 60 ^
  -an ^
  -f flv ^
  "rtmp://%RTMP_SERVER%/live/%ROBOT_ID%_%SENSOR_ID%"
goto end

:end
echo.
echo Done.
pause
endlocal
