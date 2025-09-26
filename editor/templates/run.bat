@echo off
REM ============================================================================
REM  RUN SCRIPT FOR REALISTIC MODULAR PYGAME WORLD (WINDOWS)
REM ============================================================================
REM This script automates the setup and launch process.
REM It will create a virtual environment, install dependencies, and then
REM run the world viewer. Just double-click this file to start.
REM ============================================================================

echo Checking for Python Launcher ^(py.exe^)...
py -3 --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python 3 is not installed or not in your PATH.
    echo Please install Python 3.8+ from python.org and ensure the Python Launcher is included.
    pause
    exit /b
)

echo Checking for virtual environment...
if not exist "venv" (
    echo Creating virtual environment ^(this may take a moment^)...
    py -3 -m venv venv
    if %errorlevel% neq 0 (
        echo Failed to create virtual environment.
        pause
        exit /b
    )
)

echo Activating environment and installing dependencies...
call "venv\Scripts\activate.bat"
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo Failed to install dependencies. Please check your internet connection.
    pause
    exit /b
)

echo Launching World Viewer...
py -3 run_world.py

echo.
echo Application closed. Press any key to exit.
pause