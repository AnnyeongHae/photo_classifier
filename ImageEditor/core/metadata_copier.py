# -*- coding: utf-8 -*-
"""EXIF metadata preservation for image-to-image operations via exiftool."""
from __future__ import annotations

import shutil
import subprocess
import logging
from pathlib import Path
from typing import Optional

from PIL import Image

log = logging.getLogger(__name__)

_ASSETS_ROOT = Path(__file__).parent.parent.parent / "assets"


def find_exiftool() -> Optional[str]:
    """Return path to exiftool: check bundled assets first, then PATH."""
    for name in ("exiftool.exe", "exiftool"):
        candidate = _ASSETS_ROOT / name
        if candidate.is_file():
            return str(candidate)
    return shutil.which("exiftool")


def copy_metadata_exiftool(
    src: Path,
    dst: Path,
    exiftool_path: Optional[str] = None,
) -> bool:
    """Copy all EXIF/XMP/IPTC tags from src to dst using exiftool. Returns True on success."""
    exe = exiftool_path or find_exiftool()
    if not exe:
        return False

    cmd = [
        exe,
        "-overwrite_original",
        "-TagsFromFile", str(src),
        "-all:all",
        "-unsafe",
        str(dst),
    ]
    extra: dict = {}
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        extra["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30, **extra)
        if result.returncode != 0:
            log.debug("exiftool stderr: %s", result.stderr.decode(errors="replace"))
        return result.returncode == 0
    except Exception as e:
        log.warning("exiftool failed: %s", e)
        return False


def embed_pillow_exif(dst: Path, exif_bytes: bytes, jpeg_quality: int = 92) -> bool:
    """Fallback: re-save JPEG with original EXIF bytes embedded via Pillow."""
    try:
        img = Image.open(str(dst))
        img.save(str(dst), quality=jpeg_quality, exif=exif_bytes, optimize=True)
        return True
    except Exception as e:
        log.warning("Pillow EXIF embed failed: %s", e)
        return False
