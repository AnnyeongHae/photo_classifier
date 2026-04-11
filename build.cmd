@echo off
REM ============================================================
REM  Photo Classifier - Nuitka Standalone Build Script
REM  Run from the project root directory:
REM    cd "d:\2026.04.09_photo classification"
REM    build.cmd
REM ============================================================

set PROJECT_DIR=%~dp0
set DIST_DIR=%PROJECT_DIR%dist

echo [1/3] Installing / checking build dependencies...
pip install nuitka pyside6 ordered-set zstandard --quiet

echo [2/3] Running Nuitka standalone build...
python -m nuitka ^
  --standalone ^
  --enable-plugin=pyside6 ^
  --include-data-dir="%PROJECT_DIR%assets=assets" ^
  --include-package=shapefile ^
  --include-package=core ^
  --include-package=gui ^
  --include-package=workers ^
  --windows-console-mode=disable ^
  --output-dir="%DIST_DIR%" ^
  --output-filename=PhotoClassifier.exe ^
  --jobs=4 ^
  "%PROJECT_DIR%app.py"

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Build failed.
    exit /b %ERRORLEVEL%
)

echo [3/3] Build complete!
echo Output: %DIST_DIR%\app.dist\PhotoClassifier.exe
echo.
echo NOTE: Distribute the entire app.dist\ folder (not just the .exe).
echo       The assets\ subfolder must remain alongside PhotoClassifier.exe.
pause
