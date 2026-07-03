@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=python"
if exist "D:\Anaconda3\envs\yolov5_pyqt5\python.exe" (
  set "PYTHON_EXE=D:\Anaconda3\envs\yolov5_pyqt5\python.exe"
)

"%PYTHON_EXE%" run_robot_stream_demo.py %*
