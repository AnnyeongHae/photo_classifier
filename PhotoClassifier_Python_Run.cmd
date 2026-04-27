@echo off
setlocal
chcp 65001 > nul

cd /d "%~dp0"

set "PYTHON_EXE=%~dp0venv311\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python virtual environment was not found:
    echo         %PYTHON_EXE%
    echo.
    echo Run this app from the original project folder, or recreate venv311 first.
    pause
    exit /b 1
)

"%PYTHON_EXE%" "%~dp0tools\check_runtime_deps.py"
if not "%ERRORLEVEL%"=="0" (
    echo [ERROR] Runtime dependencies are missing.
    echo.
    echo Install them with:
    echo "%PYTHON_EXE%" -m pip install -r "%~dp0requirements-runtime.txt"
    echo.
    pause
    exit /b 1
)

"%PYTHON_EXE%" "%~dp0app.py"
set "APP_RC=%ERRORLEVEL%"

if not "%APP_RC%"=="0" (
    echo.
    echo [ERROR] Photo Classifier exited with code %APP_RC%.
    pause
    exit /b %APP_RC%
)

endlocal
