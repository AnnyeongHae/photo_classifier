"""
Nuitka build helper — called by build.cmd.

Runs the Nuitka command as a Python list so that cmd.exe path-space tokenization
is bypassed entirely. Also post-copies exiftool_files\ (Nuitka excludes .dll/.exe
from --include-data-dir by design).
"""
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
ASSETS_DIR  = PROJECT_DIR / "assets"
DIST_DIR    = PROJECT_DIR / "dist"
APP_DIST    = DIST_DIR / "app.dist"


def check_assets() -> bool:
    ok = True
    checks = [
        (ASSETS_DIR / "exiftool.exe",                                          "assets\\exiftool.exe"),
        (ASSETS_DIR / "exiftool_files",                                        "assets\\exiftool_files\\"),
        (ASSETS_DIR / "my_cities.csv",                                         "assets\\my_cities.csv"),
        (ASSETS_DIR / "Natural Earth_10m_admin_0_countries" / "ne_10m_admin_0_countries.shp",
                                                                               "assets\\Natural Earth_10m_admin_0_countries\\ne_10m_admin_0_countries.shp"),
    ]
    for path, label in checks:
        if not path.exists():
            print(f"[ERROR] Required asset not found: {label}")
            ok = False
    return ok


def run_nuitka() -> int:
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--enable-plugin=pyside6",
        f"--include-data-dir={ASSETS_DIR}=assets",
        f"--include-data-files={ASSETS_DIR / 'exiftool.exe'}=assets/exiftool.exe",
        "--include-package=shapefile",
        "--include-package=core",
        "--include-package=gui",
        "--include-package=workers",
        "--windows-console-mode=disable",
        f"--output-dir={DIST_DIR}",
        "--output-filename=PhotoClassifier.exe",
        "--jobs=4",
        str(PROJECT_DIR / "app.py"),
    ]
    print("[2/4] Running Nuitka standalone build...")
    print("      " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
    return subprocess.run(cmd).returncode


def copy_exiftool_files() -> int:
    src = ASSETS_DIR / "exiftool_files"
    dst = APP_DIST / "assets" / "exiftool_files"
    print(f"[3/4] Copying ExifTool Perl runtime: {src} -> {dst}")
    try:
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        print(f"      OK: {dst} ({sum(1 for _ in dst.rglob('*'))} files)")
        return 0
    except Exception as exc:
        print(f"[ERROR] Copy failed: {exc}")
        return 1


def main() -> int:
    print("[1/4] Checking assets...")
    if not check_assets():
        return 1

    rc = run_nuitka()
    if rc != 0:
        print("[ERROR] Nuitka build failed.")
        return rc

    rc = copy_exiftool_files()
    if rc != 0:
        return rc

    exe = APP_DIST / "PhotoClassifier.exe"
    print()
    print("[4/4] Build complete!")
    print(f"      Output: {exe}")
    print()
    print("NOTE: Distribute the entire app.dist\\ folder.")
    print("      ExifTool (exe + exiftool_files\\) is bundled inside assets\\.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
