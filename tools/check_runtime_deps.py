# -*- coding: utf-8 -*-
import importlib
import sys


REQUIRED_MODULES = [
    "PySide6",
    "PIL",
    "pillow_heif",
    "shapefile",
    "cv2",
    "numpy",
    "rawpy",
    "piexif",
]


def main() -> int:
    print(f"Python: {sys.executable}")
    print(f"Version: {sys.version.split()[0]}")
    ok = True
    for module_name in REQUIRED_MODULES:
        try:
            module = importlib.import_module(module_name)
            version = getattr(module, "__version__", "")
            suffix = f" {version}" if version else ""
            print(f"OK   {module_name}{suffix}")
        except Exception as exc:
            ok = False
            print(f"FAIL {module_name}: {type(exc).__name__}: {exc}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
