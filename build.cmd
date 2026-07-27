@echo off
REM Photo Classifier - Nuitka Standalone Build
REM Run from the project root: build.cmd
REM
REM Required assets before building:
REM   assets\exiftool.exe
REM   assets\exiftool_files\
REM   assets\my_cities.csv
REM   assets\Natural Earth_10m_admin_0_countries\
REM
REM Build logic is in _build_helper.py (avoids cmd.exe space-in-path tokenization).

setlocal

cd /d "%~dp0"

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "NUITKA_CACHE_DIR_MODULE_CACHE=%~dp0.nuitka-cache\module-cache"

set "PYTHON_EXE=%~dp0venv311\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Build Python was not found:
    echo         %PYTHON_EXE%
    echo.
    echo Create venv311 with Python 3.11 and install dependencies first:
    echo py -3.11 -m venv venv311
    echo "%PYTHON_EXE%" -m pip install -r requirements-runtime.txt -r requirements-build.txt
    echo.
    pause
    exit /b 1
)

"%PYTHON_EXE%" _build_helper.py
set "BUILD_RC=%ERRORLEVEL%"

if not "%BUILD_RC%"=="0" (
    endlocal
    exit /b %BUILD_RC%
)

endlocal
pause
