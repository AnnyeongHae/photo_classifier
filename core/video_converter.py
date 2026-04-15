# -*- coding: utf-8 -*-
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional
import threading

logger = logging.getLogger("photo_classifier")

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".3gp", ".osv"}

def _resolve_executable(exe_name: str) -> Optional[str]:
    """Find the executable in assets or system path."""
    if getattr(sys, 'frozen', False):
        assets_dir = Path(sys.executable).parent / "assets"
    else:
        assets_dir = Path(__file__).parent.parent / "assets"

    exe_file = exe_name + (".exe" if os.name == 'nt' else "")

    # Try direct path
    exe_path = assets_dir / exe_file
    if exe_path.is_file():
        return str(exe_path)
        
    # Try recursive search within assets
    if assets_dir.exists():
        found = list(assets_dir.rglob(exe_file))
        if found:
            return str(found[0])
    
    # Try system PATH
    sys_exe = shutil.which(exe_name)
    if sys_exe:
        return sys_exe
        
    return None

def resolve_ffmpeg_path() -> str:
    path = _resolve_executable("ffmpeg")
    if not path:
        raise FileNotFoundError("FFmpeg executable not found. Place it in the assets folder or system PATH.")
    return path

def resolve_ffprobe_path() -> str:
    path = _resolve_executable("ffprobe")
    if not path:
        raise FileNotFoundError("FFprobe executable not found. Place it in the assets folder or system PATH.")
    return path

def get_video_resolution(ffprobe_path: str, file_path: Path) -> tuple[int, int]:
    """Returns (width, height). Returns (0,0) if it fails."""
    cmd = [
        ffprobe_path,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json",
        str(file_path)
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        data = json.loads(res.stdout)
        stream = data.get("streams", [{}])[0]
        w = int(stream.get("width", 0))
        h = int(stream.get("height", 0))
        return w, h
    except Exception as e:
        logger.error(f"Error reading resolution for {file_path}: {e}")
        return 0, 0

class VideoConverterConfig:
    def __init__(self, input_folder: Path, output_folder: Path, max_width: int, max_height: int):
        self.input_folder = input_folder
        self.output_folder = output_folder
        self.max_width = max_width
        self.max_height = max_height

class VideoConverterResult:
    def __init__(self):
        self.success = 0
        self.skipped = 0
        self.failed = 0
        self.cancelled = False

def run_video_conversion(
    config: VideoConverterConfig,
    progress_cb: Callable[[str, int, int, dict], None] = None,
    cancel_flag: threading.Event = None
) -> VideoConverterResult:
    
    result = VideoConverterResult()
    stats = {"success": 0, "skipped": 0, "failed": 0, "duplicates": 0}
    
    ffmpeg_path = resolve_ffmpeg_path()
    ffprobe_path = resolve_ffprobe_path()
    from core.extractor import resolve_exiftool_path
    exiftool_path = resolve_exiftool_path()
    if not exiftool_path:
        raise FileNotFoundError("ExifTool executable not found.")

    if progress_cb:
        progress_cb("scanning", 0, 0, stats)
        
    all_files = []
    # Find all videos
    for root, dirs, files in os.walk(config.input_folder):
        for f in files:
            p = Path(root) / f
            if p.suffix.lower() in VIDEO_EXTENSIONS:
                all_files.append(p)
                
    total_files = len(all_files)
    if progress_cb:
        progress_cb("scanning", total_files, total_files, stats)
        
    failed_folder = config.output_folder / "_Failed_Conversions"
    
    for i, file_path in enumerate(all_files):
        if cancel_flag and cancel_flag.is_set():
            result.cancelled = True
            break
            
        if progress_cb:
            progress_cb(f"Processing {file_path.name}", i, total_files, stats)
            
        w, h = get_video_resolution(ffprobe_path, file_path)
        
        if w == 0 or h == 0:
            logger.warning(f"Skipping {file_path}: Could not read resolution.")
            stats["skipped"] += 1
            continue
            
        # Check if needs scale
        if w > config.max_width or h > config.max_height:
            # Need to convert
            out_path = config.output_folder / file_path.name
            
            # Prevent overwrite natively, append suffix
            idx = 1
            while out_path.exists():
                out_path = config.output_folder / f"{file_path.stem}_{idx}{file_path.suffix}"
                idx += 1
                
            scale_filter = f"scale='min({config.max_width},iw)':'min({config.max_height},ih)'"
            
            # Construct FFmpeg command
            cmd_ffmpeg = [
                ffmpeg_path,
                "-y", "-i", str(file_path),
                "-vf", scale_filter,
                "-c:v", "libx264",
                "-crf", "23",
                "-preset", "medium",
                "-c:a", "copy",
                "-map_metadata", "0",
                str(out_path)
            ]
            
            logger.info(f"Converting {file_path.name}")
            try:
                subprocess.run(
                    cmd_ffmpeg, 
                    check=True, 
                    capture_output=True, 
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                
                # ExifTool Injection (Overwrites original output with strictly copied metadata)
                cmd_exif = [
                    exiftool_path,
                    "-tagsFromFile", str(file_path),
                    "-All:All",
                    "-overwrite_original",
                    str(out_path)
                ]
                subprocess.run(
                    cmd_exif, 
                    check=True, 
                    capture_output=True, 
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                
                stats["success"] += 1
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed converting {file_path.name}: {e.stderr if hasattr(e, 'stderr') else e}")
                stats["failed"] += 1
                failed_folder.mkdir(parents=True, exist_ok=True)
                # Keep original intact, but log the failure
                with open(failed_folder / f"{file_path.name}_FAILED.txt", "w", encoding="utf-8") as err_f:
                    err_f.write(f"Failed to convert: {file_path}\nError: {e}\n")
                if out_path.exists():
                    out_path.unlink()
        else:
            # Resolution is small enough, skip converting it
            logger.info(f"Skipping {file_path.name} (Resolution: {w}x{h})")
            stats["skipped"] += 1

        if progress_cb:
            progress_cb("Converting", i + 1, total_files, stats)

    result.success = stats["success"]
    result.skipped = stats["skipped"]
    result.failed = stats["failed"]
    
    return result
