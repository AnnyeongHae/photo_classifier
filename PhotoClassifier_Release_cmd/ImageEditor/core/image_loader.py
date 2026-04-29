# -*- coding: utf-8 -*-
"""Multi-format image loader: standard (Pillow) + RAW (rawpy/LibRaw) + HEIC (pillow-heif)."""
from __future__ import annotations

import io
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image

RAW_EXTENSIONS: frozenset[str] = frozenset({
    # Sony
    ".arw", ".srf", ".sr2",
    # Canon
    ".cr2", ".cr3", ".crw",
    # Nikon
    ".nef", ".nrw",
    # Adobe / Generic
    ".dng",
    # Panasonic
    ".rw2",
    # Olympus
    ".orf",
    # Fujifilm
    ".raf",
    # Pentax
    ".pef", ".ptx",
    # Samsung (camera RAW, not phone)
    ".srw",
    # Epson
    ".erf",
    # Minolta / Konica
    ".mrw",
    # Sigma
    ".x3f",
    # Hasselblad
    ".3fr",
    # Kodak
    ".kdc", ".k25",
    # Mamiya
    ".mef",
    # Leica
    ".rwl",
    # Phase One
    ".iiq",
    # Nokia
    ".nrw",
})

STANDARD_EXTENSIONS: frozenset[str] = frozenset({
    ".jpg", ".jpeg", ".jpe", ".jfif",
    ".png",
    ".gif",
    ".bmp", ".dib",
    ".tif", ".tiff",
    ".webp",
    ".heic", ".heif",
    ".ico",
    ".ppm", ".pgm", ".pbm", ".pnm",
    ".tga",
    ".pcx",
    ".xbm",
    ".jp2", ".j2k", ".jpf", ".jpx",
})

SUPPORTED_EXTENSIONS: frozenset[str] = RAW_EXTENSIONS | STANDARD_EXTENSIONS


def load_image(
    path: Path,
    preview_only: bool = False,
) -> Tuple[Image.Image, Optional[bytes]]:
    """
    Load an image file into a PIL Image (RGB mode).

    Returns (image, exif_bytes).  exif_bytes is None for RAW files
    (EXIF is handled separately by exiftool in that case).

    preview_only=True uses the embedded JPEG thumbnail for RAW files —
    fast but lower resolution.  Always False during batch processing.
    """
    ext = path.suffix.lower()
    if ext in RAW_EXTENSIONS:
        return _load_raw(path, preview_only=preview_only)
    return _load_standard(path)


def _load_raw(path: Path, preview_only: bool) -> Tuple[Image.Image, Optional[bytes]]:
    try:
        import rawpy
    except ImportError as exc:
        raise ValueError(
            f"RAW 파일({path.suffix})을 열려면 rawpy가 필요합니다.\n"
            "설치: pip install rawpy"
        ) from exc

    with rawpy.imread(str(path)) as raw:
        if preview_only:
            try:
                thumb = raw.extract_thumb()
                if thumb.format == rawpy.ThumbFormat.JPEG:
                    return Image.open(io.BytesIO(thumb.data)).convert("RGB"), None
                if thumb.format == rawpy.ThumbFormat.BITMAP:
                    return Image.fromarray(thumb.data).convert("RGB"), None
            except Exception:
                pass  # fall through to full processing

        rgb = raw.postprocess(
            use_camera_wb=True,
            no_auto_bright=False,
            output_bps=8,
        )
        return Image.fromarray(rgb), None  # EXIF via exiftool only


def _load_standard(path: Path) -> Tuple[Image.Image, Optional[bytes]]:
    ext = path.suffix.lower()

    if ext in (".heic", ".heif"):
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except ImportError as exc:
            raise ValueError(
                "HEIC/HEIF 파일을 열려면 pillow-heif가 필요합니다.\n"
                "설치: pip install pillow-heif"
            ) from exc

    img = Image.open(str(path))

    exif_bytes: Optional[bytes] = img.info.get("exif")

    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        return bg, exif_bytes

    if img.mode != "RGB":
        return img.convert("RGB"), exif_bytes

    return img, exif_bytes


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def get_image_files(folder: Path) -> list[Path]:
    """Return all supported image files in folder (non-recursive), sorted by name."""
    return sorted(
        (p for p in folder.iterdir() if p.is_file() and is_supported(p)),
        key=lambda p: p.name.lower(),
    )
