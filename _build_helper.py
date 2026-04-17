"""
Nuitka build helper -- called by build.cmd.

All output (print statements + Nuitka subprocess) is tee'd to build.log so
every error is preserved in one place even after the terminal closes.
"""
# -*- coding: utf-8 -*-
import os
import shutil
import stat
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
ASSETS_DIR  = PROJECT_DIR / "assets"
DIST_DIR    = PROJECT_DIR / "dist"
APP_DIST    = DIST_DIR / "app.dist"
RELEASE_DIR = PROJECT_DIR / "PhotoClassifier_Release"
LOG_FILE    = PROJECT_DIR / "build.log"


# ── tee: write to console AND log file simultaneously ─────────────────────────

class _Tee:
    def __init__(self, original, log_file):
        self._orig = original
        self._log  = log_file

    def write(self, s: str) -> None:
        self._orig.write(s)
        self._log.write(s)

    def flush(self) -> None:
        self._orig.flush()
        self._log.flush()

    def __getattr__(self, name):
        return getattr(self._orig, name)


# ── helpers ───────────────────────────────────────────────────────────────────

def _force_remove(path: Path) -> None:
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


def _run_streamed(cmd: list) -> int:
    """Run a subprocess and stream its output through sys.stdout (captured by tee)."""
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    for line in iter(process.stdout.readline, ""):
        print(line, end="", flush=True)
    process.stdout.close()
    process.wait()
    return process.returncode


def _copy_item(label: str, src: Path, dst: Path) -> int:
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

def step_install_deps() -> int:
    """[0/5] Install / verify build dependencies via pip."""
    print("[0/5] Installing build dependencies...")
    rc = _run_streamed([
        sys.executable, "-m", "pip", "install",
        "-r", str(PROJECT_DIR / "requirements-build.txt"),
        "--quiet",
    ])
    if rc != 0:
        print("[ERROR] pip install failed.")
    else:
        print("      Done.")
    return rc


def step_clean() -> None:
    """[1/5] Remove dist/app.dist to avoid PermissionError on stale locked files."""
    if APP_DIST.exists():
        print(f"[1/5] Cleaning previous build: {APP_DIST}")
        _force_remove(APP_DIST)
        print("      Done.")
    else:
        print("[1/5] No previous build to clean.")


def step_check_assets() -> bool:
    """[2/5] Verify required source assets exist before spending time building."""
    print("[2/5] Checking assets...")
    ok = True
    required = [
        (ASSETS_DIR / "exiftool.exe",
         "assets\\exiftool.exe"),
        (ASSETS_DIR / "exiftool_files",
         "assets\\exiftool_files\\"),
        (ASSETS_DIR / "my_cities.csv",
         "assets\\my_cities.csv"),
        (ASSETS_DIR / "Natural Earth_10m_admin_0_countries" / "ne_10m_admin_0_countries.shp",
         "assets\\Natural Earth_10m_admin_0_countries\\ne_10m_admin_0_countries.shp"),
    ]
    for path, label in required:
        if path.exists():
            print(f"      OK : {label}")
        else:
            print(f"[ERROR] Missing required asset: {label}")
            ok = False

    for exe in ["ffmpeg.exe", "ffprobe.exe"]:
        if (ASSETS_DIR / exe).exists() or list(ASSETS_DIR.rglob(exe)):
            print(f"      OK : assets\\{exe}")
        else:
            print(f"[WARN] Optional asset missing: assets\\{exe} — video converter may not work")

    return ok


def step_nuitka() -> int:
    """[3/5] Run Nuitka standalone build."""
    # Cap at 16 to avoid RAM pressure on machines with many cores.
    jobs = min(os.cpu_count() or 4, 16)

    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--enable-plugin=pyside6",

        # ── Speed: LTO is the biggest time sink in standalone builds ──────────
        # Disabling cuts 30-60% off build time; runtime impact is negligible for
        # a GUI app of this size.
        "--lto=no",

        # ── Inclusions ────────────────────────────────────────────────────────
        # .exe/.dll and space-in-path assets are handled in step_copy_assets().
        f"--include-data-dir={ASSETS_DIR}=assets",
        # Force-include local packages so all submodules are compiled even when
        # referenced only via getattr / importlib-style dynamic imports.
        "--include-package=core",
        "--include-package=gui",
        "--include-package=workers",
        # shapefile: auto-traced via `import shapefile` in core/mvp.py.
        # LivePhotoConverter: auto-traced via explicit imports in live_photo_worker.py.
        # Neither needs --include-package; force-including LivePhotoConverter
        # would pull in setup.py → setuptools → ~344 extra compiled files.
        "--noinclude-setuptools-mode=nofollow",
        "--noinclude-pytest-mode=nofollow",

        # ── Bytecode size reduction ───────────────────────────────────────────
        "--python-flag=no_docstrings",
        "--python-flag=no_asserts",   # equivalent to -O; safe for production GUI

        "--windows-console-mode=disable",
        f"--output-dir={DIST_DIR}",
        "--output-filename=PhotoClassifier.exe",
        f"--jobs={jobs}",
        str(PROJECT_DIR / "app.py"),
    ]

    print(f"[3/5] Running Nuitka (jobs={jobs}, lto=off)...")
    print("      " + " ".join(f'"{c}"' if " " in c else c for c in cmd))

    return _run_streamed(cmd)


def step_copy_assets() -> int:
    """[4/5] Explicitly copy assets Nuitka may miss (space-in-path, .exe/.dll)."""
    print("[4/5] Copying data assets...")
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

    for exe in ["ffmpeg.exe", "ffprobe.exe"]:
        src = ASSETS_DIR / exe
        if not src.exists():
            found = list(ASSETS_DIR.rglob(exe))
            if found:
                src = found[0]
            else:
                continue
        items.append((exe, src, assets_dst / exe))

    rc = 0
    for label, src, dst in items:
        rc |= _copy_item(label, src, dst)
    return rc


def step_create_release() -> int:
    """[5/5] Package dist into a distributable release folder."""
    print("[5/5] Creating release package...")
    try:
        if RELEASE_DIR.exists():
            _force_remove(RELEASE_DIR)
        RELEASE_DIR.mkdir(parents=True, exist_ok=True)

        bin_dir = RELEASE_DIR / "bin"
        print("      Moving app.dist → bin/")
        shutil.move(str(APP_DIST), str(bin_dir))

        manual = PROJECT_DIR / "사용방법.txt"
        if manual.exists():
            shutil.copy2(manual, RELEASE_DIR / "사용방법.txt")
            print("      Copied 사용방법.txt")
        else:
            print("[WARN] 사용방법.txt not found — skipping")

        bat_path = RELEASE_DIR / "PhotoClassifier_실행하기.bat"
        with bat_path.open("w", encoding="euc-kr") as fp:
            fp.write("@echo off\n")
            fp.write("chcp 65001 > nul\n")
            fp.write('start "" "%~dp0bin\\PhotoClassifier.exe"\n')
        print("      Created launcher: PhotoClassifier_실행하기.bat")
        return 0
    except Exception as exc:
        print(f"[ERROR] Release packaging failed: {exc}")
        return 1


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> int:
    rc = step_install_deps()
    if rc != 0:
        return rc

    step_clean()

    if not step_check_assets():
        return 1

    rc = step_nuitka()
    if rc != 0:
        print("[ERROR] Nuitka build failed — check build.log for the full error.")
        return rc

    rc = step_copy_assets()
    if rc != 0:
        return rc

    rc = step_create_release()
    if rc != 0:
        return rc

    print()
    print("Build complete!")
    print(f"  Release : {RELEASE_DIR}")
    print()
    print("Distribute: zip 'PhotoClassifier_Release' and share.")
    print("Users run : PhotoClassifier_실행하기.bat")
    return 0


if __name__ == "__main__":
    log_file = LOG_FILE.open("w", encoding="utf-8", errors="replace")
    started  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_file.write(f"=== Build started {started} ===\n\n")

    sys.stdout = _Tee(sys.__stdout__, log_file)
    sys.stderr = _Tee(sys.__stderr__, log_file)

    try:
        rc = main()
    except Exception as exc:
        import traceback
        print(f"\n[FATAL] Unexpected error: {exc}")
        traceback.print_exc()
        rc = 1
    finally:
        ended = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        log_file.write(f"\n=== Build ended {ended} (rc={rc}) ===\n")
        log_file.close()

    print(f"\nLog: {LOG_FILE}")
    sys.exit(rc)
