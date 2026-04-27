"""
ZIP Archive auto-extraction logic.
Finds ZIP files, unzips supported media, and moves the original ZIP.
"""
# -*- coding: utf-8 -*-
import os
import shutil
import threading
import zipfile
from pathlib import Path
from typing import Callable, Optional

from core.extractor import SUPPORTED_EXTENSIONS
from core.logging_config import get_logger

logger = get_logger(__name__)


def _safe_member_path(base_dir: Path, member_name: str) -> Optional[Path]:
    """Return a safe extraction path, or None for unsafe ZIP members."""
    normalized = member_name.replace("\\", "/")
    member_path = Path(normalized)
    if member_path.is_absolute() or ".." in member_path.parts:
        return None

    target = (base_dir / member_path).resolve()
    base = base_dir.resolve()
    try:
        target.relative_to(base)
    except ValueError:
        return None
    return target


def expand_archives(
    input_folder: Path,
    cancel_flag: Optional[threading.Event] = None,
    progress_cb: Optional[Callable[[str, int, int, dict], None]] = None,
) -> None:
    """
    Finds all .zip files in the input_folder recursively (skipping _Processed_ZIPs).
    Extracts files with SUPPORTED_EXTENSIONS into a hidden .unzipped directory.
    Moves the processed .zip files to _Processed_ZIPs.
    """
    zip_files = []
    
    # 1. Collect all zip files
    for root, dirs, files in os.walk(input_folder):
        # Skip our special folders
        if "_Processed_ZIPs" in dirs:
            dirs.remove("_Processed_ZIPs")
        if ".unzipped" in dirs:
            dirs.remove(".unzipped")
            
        for f in files:
            if f.lower().endswith(".zip"):
                zip_files.append(Path(root) / f)

    total_zips = len(zip_files)
    if total_zips == 0:
        return

    logger.info(f"Found {total_zips} ZIP files. Expanding...")
    
    processed_dir = input_folder / "_Processed_ZIPs"
    unzipped_dir = input_folder / ".unzipped"
    
    processed_dir.mkdir(parents=True, exist_ok=True)
    unzipped_dir.mkdir(parents=True, exist_ok=True)

    extracted_count = 0
    
    for idx, zip_path in enumerate(zip_files):
        if cancel_flag and cancel_flag.is_set():
            logger.warning("Pipeline cancelled during archive expansion")
            raise RuntimeError("Pipeline cancelled by user")

        if progress_cb:
            progress_cb("expand_archives", idx, total_zips, None)

        logger.debug(f"Extracting {zip_path.name}")
        
        target_subfolder = unzipped_dir / zip_path.stem
        
        collision_idx = 1
        while target_subfolder.exists():
            target_subfolder = unzipped_dir / f"{zip_path.stem}_{collision_idx}"
            collision_idx += 1

        target_subfolder.mkdir(parents=True, exist_ok=True)
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for zinfo in zf.infolist():
                    if cancel_flag and cancel_flag.is_set():
                        raise RuntimeError("Pipeline cancelled by user")
                    
                    if zinfo.is_dir():
                        continue
                        
                    target_path = _safe_member_path(target_subfolder, zinfo.filename)
                    if target_path is None:
                        logger.warning(f"Skipping unsafe ZIP member: {zinfo.filename}")
                        continue

                    ext = target_path.suffix.lower()
                    if ext in SUPPORTED_EXTENSIONS:
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(zinfo) as src, target_path.open("wb") as dst:
                            shutil.copyfileobj(src, dst)
                        extracted_count += 1
                        
            # Move the original ZIP to _Processed_ZIPs
            dest_zip = processed_dir / zip_path.name
            collision_idx = 1
            while dest_zip.exists():
                dest_zip = processed_dir / f"{zip_path.stem}_{collision_idx}.zip"
                collision_idx += 1
                
            shutil.move(str(zip_path), str(dest_zip))
            logger.info(f"Moved {zip_path.name} to {dest_zip}")
            
        except zipfile.BadZipFile:
            logger.error(f"Bad ZIP file: {zip_path}")
        except Exception as e:
            logger.error(f"Failed to extract {zip_path}: {e}")

    if progress_cb:
        progress_cb("expand_archives", total_zips, total_zips, None)

    logger.info(f"Archive expansion complete. Extracted {extracted_count} supported files.")
