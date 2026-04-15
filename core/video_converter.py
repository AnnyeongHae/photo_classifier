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

def get_video_duration(ffprobe_path: str, file_path: Path) -> float:
    cmd = [
        ffprobe_path,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(file_path)
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        return float(res.stdout.strip())
    except Exception:
        return 0.0

def _parse_ffmpeg_time(time_str: str) -> float:
    # time_str is like '00:00:23.45'
    try:
        h, m, s = time_str.split(':')
        return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception:
        return 0.0

def detect_hardware_encoder(ffmpeg_path: str, work_dir: Path, codec: str = "h264") -> str:
    """Detects available hardware encoder for the chosen codec."""
    if codec.lower() == "hevc":
        encoders = ["hevc_nvenc", "hevc_qsv", "hevc_amf", "libx265"]
    else:
        encoders = ["h264_nvenc", "h264_qsv", "h264_amf", "libx264"]
        
    for enc in encoders:
        if enc in ["libx264", "libx265"]:
            return enc
        test_file = work_dir / f"test_enc_{enc}.mp4"
        cmd = [
            ffmpeg_path, "-y", "-f", "lavfi", "-i", "color=c=black:s=128x128", 
            "-vframes", "1", "-c:v", enc, str(test_file)
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            if test_file.exists():
                test_file.unlink()
            if res.returncode == 0:
                logger.info(f"Hardware encoder detected: {enc}")
                return enc
        except Exception:
            pass
    return "libx265" if codec.lower() == "hevc" else "libx264"

class VideoConverterConfig:
    def __init__(self, input_folder: Path, output_folder: Path, max_width: int, max_height: int, codec: str = "h264"):
        self.input_folder = input_folder
        self.output_folder = output_folder
        self.max_width = max_width
        self.max_height = max_height
        self.codec = codec

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
        progress_cb("Scanning videos...", 0, 0, stats)
        
    all_files = []
    for root, dirs, files in os.walk(config.input_folder):
        for f in files:
            p = Path(root) / f
            if p.suffix.lower() in VIDEO_EXTENSIONS:
                all_files.append(p)
                
    total_files = len(all_files)
    if progress_cb:
        progress_cb("Detecting GPU Acceleration...", total_files, total_files, stats)
        
    failed_folder = config.output_folder / "_Failed_Conversions"
    
    # 1. Detect best encoder
    best_encoder = detect_hardware_encoder(ffmpeg_path, config.output_folder, config.codec)
    
    # Encoder mapping
    # H.264
    encoder_flags = {
        "h264_nvenc": ["-c:v", "h264_nvenc", "-cq", "26", "-b:v", "0", "-preset", "p4", "-pix_fmt", "yuv420p"],
        "h264_qsv":   ["-c:v", "h264_qsv", "-global_quality", "26", "-preset", "medium", "-pix_fmt", "yuv420p"],
        "h264_amf":   ["-c:v", "h264_amf", "-quality", "balanced", "-pix_fmt", "yuv420p"],
        "libx264":    ["-c:v", "libx264", "-crf", "23", "-preset", "fast", "-pix_fmt", "yuv420p"],
        
        # HEVC / H.265 (No pix_fmt specified to allow 10-bit transparently)
        "hevc_nvenc": ["-c:v", "hevc_nvenc", "-cq", "26", "-b:v", "0", "-preset", "p4", "-tag:v", "hvc1"],
        "hevc_qsv":   ["-c:v", "hevc_qsv", "-global_quality", "26", "-preset", "medium", "-tag:v", "hvc1"],
        "hevc_amf":   ["-c:v", "hevc_amf", "-quality", "balanced", "-tag:v", "hvc1"],
        "libx265":    ["-c:v", "libx265", "-crf", "26", "-preset", "fast", "-tag:v", "hvc1"]
    }
    
    if best_encoder not in encoder_flags:
        best_encoder = "libx265" if config.codec == "hevc" else "libx264"
        
    enc_args = encoder_flags[best_encoder]
    
    for i, file_path in enumerate(all_files):
        if cancel_flag and cancel_flag.is_set():
            result.cancelled = True
            break
            
        w, h = get_video_resolution(ffprobe_path, file_path)
        
        if w == 0 or h == 0:
            logger.warning(f"Skipping {file_path}: Could not read resolution.")
            stats["skipped"] += 1
            if progress_cb:
                progress_cb(f"Skipped {file_path.name}", i + 1, total_files, stats)
            continue
            
        # Check if needs scale
        if w > config.max_width or h > config.max_height:
            out_path = config.output_folder / file_path.name
            
            idx = 1
            while out_path.exists():
                out_path = config.output_folder / f"{file_path.stem}_{idx}{file_path.suffix}"
                idx += 1
                
            scale_filter = f"scale='min({config.max_width},iw)':'min({config.max_height},ih)'"
            
            # Robust mapping to avoid Muxer crashes: drop metadata, drop subtitles/data, use only main audio/video
            cmd_ffmpeg = [
                ffmpeg_path,
                "-y", "-i", str(file_path),
                "-map", "0:v:0",   # Grab only the primary video stream
                "-map", "0:a?",    # Grab audio streams if they exist
                "-vf", scale_filter
            ] + enc_args + [
                "-c:a", "copy",    # Try to copy audio to save time
                "-sn", "-dn",      # Drop subtitle and data streams
                "-map_metadata", "-1", # Completely strip metadata so it cannot crash the MP4 muxer
                str(out_path)
            ]
            
            enc_name = "GPU" if best_encoder != "libx264" else "CPU"
            logger.info(f"Converting {file_path.name} via {enc_name} ({best_encoder})")
            
            duration = get_video_duration(ffprobe_path, file_path)
            
            process = subprocess.Popen(
                cmd_ffmpeg,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                encoding='utf-8',
                errors='replace'
            )
            
            ffmpeg_failed = False
            err_log = []
            
            # Read stderr line by line for progress
            while True:
                if cancel_flag and cancel_flag.is_set():
                    process.terminate()
                    result.cancelled = True
                    break
                    
                line = process.stderr.readline()
                if not line and process.poll() is not None:
                    break
                    
                if line:
                    err_log.append(line)
                    if "time=" in line and progress_cb and duration > 0:
                        # Parse time=xx:yy:zz.ww
                        parts = line.split("time=")
                        if len(parts) > 1:
                            time_str = parts[1].split()[0]
                            curr_time = _parse_ffmpeg_time(time_str)
                            pct = min((curr_time / duration) * 100, 100)
                            # Pass decimal progress via dict
                            stats["_current_pct"] = pct
                            progress_cb(f"Converting {file_path.name} ({pct:.1f}%)", i, total_files, stats)
            
            retcode = process.poll()
            if result.cancelled:
                break
                
            if retcode != 0:
                logger.error(f"Failed converting {file_path.name}. Exit Code: {retcode}")
                stats["failed"] += 1
                ffmpeg_failed = True
                failed_folder.mkdir(parents=True, exist_ok=True)
                with open(failed_folder / f"{file_path.name}_FAILED.txt", "w", encoding="utf-8") as err_f:
                    err_f.write(f"Failed to convert: {file_path}\nExit Code: {retcode}\n")
                    err_f.write("FFmpeg Log:\n" + "".join(err_log[-30:])) # last 30 lines
                if out_path.exists():
                    out_path.unlink()
            
            if not ffmpeg_failed:
                # ExifTool Injection
                cmd_exif = [
                    exiftool_path,
                    "-tagsFromFile", str(file_path),
                    "-All:All",
                    "-overwrite_original",
                    str(out_path)
                ]
                try:
                    subprocess.run(
                        cmd_exif, 
                        check=True, 
                        capture_output=True, 
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                    )
                    stats["success"] += 1
                except subprocess.CalledProcessError as e:
                    logger.error(f"ExifTool failed on {file_path.name}: {e}")
                    stats["failed"] += 1
                    failed_folder.mkdir(parents=True, exist_ok=True)
                    with open(failed_folder / f"{file_path.name}_EXIF_FAILED.txt", "w", encoding="utf-8") as err_f:
                        err_f.write(f"ExifTool injection failed.\nError: {e}\n")

        else:
            logger.info(f"Skipping {file_path.name} (Resolution: {w}x{h})")
            stats["skipped"] += 1

        # Clear file sub-progress
        stats["_current_pct"] = 0.0
        if progress_cb:
            progress_cb(f"Finished {file_path.name}", i + 1, total_files, stats)

    result.success = stats["success"]
    result.skipped = stats["skipped"]
    result.failed = stats["failed"]
    
    return result
