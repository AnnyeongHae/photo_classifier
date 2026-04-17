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

python _build_helper.py
set BUILD_RC=%ERRORLEVEL%

endlocal
if %BUILD_RC% neq 0 exit /b %BUILD_RC%
pause
