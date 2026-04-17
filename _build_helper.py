"""
Nuitka build helper -- called by build.cmd.

Runs the Nuitka command as a Python list so that cmd.exe path-space tokenization
is bypassed entirely. Post-build copies the three data assets that Nuitka may
exclude (.exe/.dll) or mangle (paths with spaces).
"""
# -*- coding: utf-8 -*-
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
ASSETS_DIR  = PROJECT_DIR / "assets"
DIST_DIR    = PROJECT_DIR / "dist"
APP_DIST    = DIST_DIR / "app.dist"
RELEASE_DIR = PROJECT_DIR / "PhotoClassifier_Release"


# ── helpers ───────────────────────────────────────────────────────────────────

def _force_remove(path: Path) -> None:
    """Remove a file or directory tree, clearing read-only bits first."""
    def _on_error(func, fpath, _excinfo):
        os.chmod(fpath, stat.S_IWRITE)
        func(fpath)

    if path.is_dir():
        shutil.rmtree(path, onerror=_on_error)
    elif path.exists():
        try:
            os.chmod(path, stat.S_IWRITE)
            path.unlink()
        except Exception as exc:
            print(f"[WARN] Could not remove {path}: {exc}")


def _copy_item(label: str, src: Path, dst: Path) -> int:
    """Copy a file or directory to dst, overwriting if it exists."""
    try:
        if src.is_dir():
            if dst.exists():
                _force_remove(dst)
            shutil.copytree(src, dst)
            count = sum(1 for _ in dst.rglob("*") if _.is_file())
            print(f"      OK (dir,  {count:4d} files): {dst.name}")
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                _force_remove(dst)
            shutil.copy2(src, dst)
            print(f"      OK (file, {dst.stat().st_size:>10,d} B): {dst.name}")
        return 0
    except Exception as exc:
        print(f"[ERROR] Failed to copy {label}: {exc}")
        return 1


# ── build steps ───────────────────────────────────────────────────────────────

def step_clean() -> None:
    """[0/4] Remove dist/app.dist to avoid PermissionError on stale locked files."""
    if APP_DIST.exists():
        print(f"[0/4] Cleaning previous build: {APP_DIST}")
        _force_remove(APP_DIST)
        print("      Done.")
    else:
        print("[0/4] No previous build to clean.")


def step_check_assets() -> bool:
    """[1/4] Verify required source assets exist before spending time building."""
    print("[1/4] Checking assets...")
    ok = True
    checks = [
        (ASSETS_DIR / "exiftool.exe",
         "assets\\exiftool.exe (Required)"),
        (ASSETS_DIR / "exiftool_files",
         "assets\\exiftool_files\\ (Required)"),
        (ASSETS_DIR / "my_cities.csv",
         "assets\\my_cities.csv (Required)"),
        (ASSETS_DIR / "Natural Earth_10m_admin_0_countries" / "ne_10m_admin_0_countries.shp",
         "assets\\Natural Earth_10m_admin_0_countries\\ne_10m_admin_0_countries.shp (Required)"),
    ]
    for path, label in checks:
        if path.exists():
            print(f"      OK: {label}")
        else:
            print(f"[ERROR] Required asset not found: {label}")
            ok = False
            
    # Optional assets for Video Converter
    opt_checks = [
        ("ffmpeg.exe", "assets\\ffmpeg.exe (Optional)"),
        ("ffprobe.exe", "assets\\ffprobe.exe (Optional)")
    ]
    for exe_name, label in opt_checks:
        if (ASSETS_DIR / exe_name).exists() or list(ASSETS_DIR.rglob(exe_name)):
            print(f"      OK: {label}")
        else:
            print(f"[WARN] Optional asset not found: {label} - Video converter may not work.")
            
    return ok


def step_nuitka() -> int:
    """[2/4] Run Nuitka standalone build."""
    # Use all available CPU cores for C compilation; cap at 16 to avoid RAM pressure.
    jobs = min(os.cpu_count() or 4, 16)

    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--enable-plugin=pyside6",
        # --include-data-dir for everything Nuitka can handle automatically.
        # .exe / .dll and paths with spaces are handled in step_copy_assets.
        f"--include-data-dir={ASSETS_DIR}=assets",
        # Local app packages: force-include so Nuitka compiles all submodules
        # even if some are only referenced via getattr / importlib patterns.
        "--include-package=core",
        "--include-package=gui",
        "--include-package=workers",
        # shapefile (pyshp): top-level `import shapefile` in core/mvp.py is
        # traced automatically by Nuitka — no force-include needed.
        #
        # LivePhotoConverter: same reason — explicit imports in
        # workers/live_photo_worker.py let Nuitka resolve it automatically.
        # Force-including would pull in setup.py → setuptools → ~344 extra files.
        #
        # Prevent accidental re-introduction of setuptools / test frameworks.
        "--noinclude-setuptools-mode=nofollow",
        "--noinclude-pytest-mode=nofollow",
        # Strip docstrings to reduce output size and speed up bytecode compile.
        "--python-flag=no_docstrings",
        "--windows-console-mode=disable",
        f"--output-dir={DIST_DIR}",
        "--output-filename=PhotoClassifier.exe",
        f"--jobs={jobs}",
        str(PROJECT_DIR / "app.py"),
    ]
    print("[2/4] Running Nuitka standalone build...")
    print("      " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
    return subprocess.run(cmd).returncode


def step_copy_assets() -> int:
    """[3/4] Explicitly copy the 3 assets Nuitka may miss or mangle."""
    print("[3/4] Copying data assets...")
    assets_dst = APP_DIST / "assets"
    assets_dst.mkdir(parents=True, exist_ok=True)

    items = [
        ("exiftool.exe",
         ASSETS_DIR / "exiftool.exe",
         assets_dst / "exiftool.exe"),
        ("my_cities.csv",
         ASSETS_DIR / "my_cities.csv",
         assets_dst / "my_cities.csv"),
        ("Natural Earth_10m_admin_0_countries",
         ASSETS_DIR / "Natural Earth_10m_admin_0_countries",
         assets_dst / "Natural Earth_10m_admin_0_countries"),
        ("exiftool_files",
         ASSETS_DIR / "exiftool_files",
         assets_dst / "exiftool_files"),
    ]
    
    # Find ffmpeg and ffprobe anywhere in ASSETS_DIR and copy to assets_dst directly
    for exe in ["ffmpeg.exe", "ffprobe.exe"]:
        if (ASSETS_DIR / exe).exists():
            items.append((exe, ASSETS_DIR / exe, assets_dst / exe))
        else:
            found = list(ASSETS_DIR.rglob(exe))
            if found:
                items.append((exe, found[0], assets_dst / exe))

    rc = 0
    for label, src, dst in items:
        rc |= _copy_item(label, src, dst)
    return rc


def step_create_release() -> int:
    """[4/5] Package everything into an intuitive release folder structure."""
    print("[4/5] Creating release structure...")
    try:
        if RELEASE_DIR.exists():
            _force_remove(RELEASE_DIR)
        RELEASE_DIR.mkdir(parents=True, exist_ok=True)
        
        # 1. Move/Copy app.dist into bin/
        bin_dir = RELEASE_DIR / "bin"
        print("      Moving app.dist to bin...")
        shutil.move(str(APP_DIST), str(bin_dir))
        
        # 2. Copy user manual txt
        readme_src = PROJECT_DIR / "사용방법.txt"
        if readme_src.exists():
            shutil.copy2(readme_src, RELEASE_DIR / "사용방법.txt")
            print("      Copied 사용방법.txt")
            
        # 3. Create Launcher bat
        bat_path = RELEASE_DIR / "PhotoClassifier_실행하기.bat"
        with bat_path.open("w", encoding="euc-kr") as fp:
            fp.write("@echo off\n")
            fp.write("chcp 65001 > nul\n")
            fp.write('start "" "%~dp0bin\\PhotoClassifier.exe"\n')
        print("      Created launcher script")
        return 0
    except Exception as exc:
        print(f"[ERROR] Release packaging failed: {exc}")
        return 1


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    step_clean()

    if not step_check_assets():
        return 1

    rc = step_nuitka()
    if rc != 0:
        print("[ERROR] Nuitka build failed.")
        return rc

    rc = step_copy_assets()
    if rc != 0:
        return rc

    rc = step_create_release()
    if rc != 0:
        return rc

    print()
    print("[5/5] Build complete!")
    print(f"      Output Folder : {RELEASE_DIR}")
    print()
    print("NOTE: Distribute the 'PhotoClassifier_Release' folder as a ZIP.")
    print("      Users just need to run 'PhotoClassifier_실행하기.bat'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
