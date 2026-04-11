"""
Nuitka build helper -- called by build.cmd.

Runs the Nuitka command as a Python list so that cmd.exe path-space tokenization
is bypassed entirely. Post-build copies the three data assets that Nuitka may
exclude (.exe/.dll) or mangle (paths with spaces).
"""
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
         "assets\\exiftool.exe"),
        (ASSETS_DIR / "exiftool_files",
         "assets\\exiftool_files\\"),
        (ASSETS_DIR / "my_cities.csv",
         "assets\\my_cities.csv"),
        (ASSETS_DIR / "Natural Earth_10m_admin_0_countries" / "ne_10m_admin_0_countries.shp",
         "assets\\Natural Earth_10m_admin_0_countries\\ne_10m_admin_0_countries.shp"),
    ]
    for path, label in checks:
        if path.exists():
            print(f"      OK: {label}")
        else:
            print(f"[ERROR] Required asset not found: {label}")
            ok = False
    return ok


def step_nuitka() -> int:
    """[2/4] Run Nuitka standalone build."""
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--enable-plugin=pyside6",
        # --include-data-dir for everything Nuitka can handle automatically.
        # .exe / .dll and paths with spaces are handled in step_copy_assets.
        f"--include-data-dir={ASSETS_DIR}=assets",
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

    rc = 0
    for label, src, dst in items:
        rc |= _copy_item(label, src, dst)
    return rc


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

    exe = APP_DIST / "PhotoClassifier.exe"
    print()
    print("[4/4] Build complete!")
    print(f"      Output : {exe}")
    print()
    print("NOTE: Distribute the entire app.dist\\ folder.")
    print("      assets\\ contains: exiftool.exe, exiftool_files\\,")
    print("                        my_cities.csv, Natural Earth_10m_admin_0_countries\\")
    return 0


if __name__ == "__main__":
    sys.exit(main())
