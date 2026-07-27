# -*- coding: utf-8 -*-
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional
from queue import Queue

logger = logging.getLogger("photo_classifier")

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".3gp", ".osv"}

# 플랫폼별 subprocess 플래그
SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

# 기본 설정값
DEFAULT_GPU_ERROR_LOG_LINES = 30
DEFAULT_MAX_CONCURRENT_ENCODES = 2
DEFAULT_FILENAME_CONFLICT_ATTEMPTS = 100

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
        res = subprocess.run(cmd, capture_output=True, text=True, check=True, creationflags=SUBPROCESS_FLAGS)
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
        res = subprocess.run(cmd, capture_output=True, text=True, check=True, creationflags=SUBPROCESS_FLAGS)
        return float(res.stdout.strip())
    except Exception as e:
        logger.warning(f"Error reading duration for {file_path}: {e}")
        return 0.0

def _parse_ffmpeg_time(time_str: str) -> float:
    """Parse FFmpeg time format (HH:MM:SS.ms) to seconds."""
    try:
        h, m, s = time_str.split(':')
        return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception:
        return 0.0

class EncoderConfig:
    """Encoder configuration for different codec/encoder combinations.

    Quality parameter (CRF/CQ):
      18 = 고화질  — visually transparent, nearly indistinguishable from source
      23 = 균형    — good quality, noticeably smaller files (FFmpeg default)
      28 = 용량 절약 — visible degradation on detailed scenes, very small files

    Note: AMD AMF does not support CQ/CRF directly. It uses fixed-QP mode (-qp_i/p/b)
    as the closest equivalent.
    """

    @classmethod
    def get_encoder_args(cls, encoder: str, quality: int = 18) -> list:
        """Build encoder arguments for the specified encoder and quality value."""
        q = str(quality)
        table = {
            # --- H.264 encoders ---
            "h264_nvenc": ["-c:v", "h264_nvenc", "-cq", q,       "-b:v", "0", "-preset", "p4",     "-pix_fmt", "yuv420p"],
            "h264_qsv":   ["-c:v", "h264_qsv",   "-global_quality", q, "-look_ahead", "1", "-preset", "medium", "-pix_fmt", "yuv420p"],
            "h264_amf":   ["-c:v", "h264_amf",   "-qp_i", q, "-qp_p", q, "-qp_b", q,                           "-pix_fmt", "yuv420p"],
            "libx264":    ["-c:v", "libx264",     "-crf", q,      "-preset", "medium",              "-pix_fmt", "yuv420p"],
            # --- H.265 / HEVC encoders ---
            "hevc_nvenc": ["-c:v", "hevc_nvenc",  "-cq", q,       "-b:v", "0", "-preset", "p4",     "-tag:v", "hvc1"],
            "hevc_qsv":   ["-c:v", "hevc_qsv",    "-global_quality", q, "-look_ahead", "1", "-preset", "medium", "-tag:v", "hvc1"],
            "hevc_amf":   ["-c:v", "hevc_amf",    "-qp_i", q, "-qp_p", q, "-qp_b", q,                           "-tag:v", "hvc1"],
            "libx265":    ["-c:v", "libx265",      "-crf", q,     "-preset", "medium",              "-tag:v", "hvc1"],
        }
        return table.get(encoder, table["libx264"])

class ThreadSafeStats:
    """Thread-safe statistics tracking."""
    def __init__(self):
        self._lock = threading.Lock()
        self._stats = {"success": 0, "skipped": 0, "failed": 0, "duplicates": 0, "_current_pct": 0.0}
    
    def increment(self, key: str, value: int = 1):
        """Increment a stat counter."""
        with self._lock:
            self._stats[key] = self._stats.get(key, 0) + value
    
    def set(self, key: str, value):
        """Set a stat value."""
        with self._lock:
            self._stats[key] = value
    
    def get_all(self) -> dict:
        """Get a copy of all stats."""
        with self._lock:
            return self._stats.copy()
    
    def get(self, key: str, default=None):
        """Get a specific stat value."""
        with self._lock:
            return self._stats.get(key, default)


class ProcessRegistry:
    """Tracks concurrently running subprocesses so cancellation reaches all of them."""

    def __init__(self):
        self._lock = threading.Lock()
        self._processes = set()

    def register(self, process: subprocess.Popen) -> None:
        with self._lock:
            self._processes.add(process)

    def unregister(self, process: subprocess.Popen) -> None:
        with self._lock:
            self._processes.discard(process)

    def terminate_all(self) -> None:
        with self._lock:
            processes = list(self._processes)
        for process in processes:
            if process.poll() is not None:
                continue
            try:
                process.terminate()
            except Exception:
                logger.debug("Failed to terminate ffmpeg process", exc_info=True)

def _try_encoder(ffmpeg_path: str, enc: str, cmd: list, test_file: Path) -> tuple[bool, str]:
    """Run one encoder test command. Returns (success, stderr_snippet)."""
    try:
        res = subprocess.run(cmd, capture_output=True, creationflags=SUBPROCESS_FLAGS, timeout=15)
        if test_file.exists():
            test_file.unlink()
        stderr = res.stderr.decode('utf-8', errors='replace') if isinstance(res.stderr, bytes) else str(res.stderr)
        if res.returncode == 0:
            return True, ""
        return False, stderr.strip()[-400:]
    except subprocess.TimeoutExpired:
        if test_file.exists():
            test_file.unlink()
        return False, "timeout"
    except Exception as e:
        if test_file.exists():
            test_file.unlink()
        return False, str(e)


def detect_hardware_encoder(ffmpeg_path: str, work_dir: Path, codec: str = "h264") -> str:
    """Detects available hardware encoder for the chosen codec.

    Tries GPU encoders first, falls back to CPU software encoders only if all GPU attempts fail.
    All failures are logged at INFO level so the user can diagnose GPU issues.
    """
    if codec.lower() == "hevc":
        gpu_encoders = ["hevc_nvenc", "hevc_qsv", "hevc_amf"]
        cpu_encoder = "libx265"
    else:
        gpu_encoders = ["h264_nvenc", "h264_qsv", "h264_amf"]
        cpu_encoder = "libx264"

    # Ensure work_dir exists — if it doesn't, the test file write fails and every
    # encoder looks broken even if the GPU is perfectly healthy.
    work_dir.mkdir(parents=True, exist_ok=True)

    for enc in gpu_encoders:
        test_file = work_dir / f"test_enc_{enc}.mp4"
        # -pix_fmt yuv420p must be specified explicitly: NVENC refuses to auto-convert
        # pixel formats and returns EINVAL (-22) without it. Other encoders (QSV, libx264)
        # are more permissive, which is why they passed the test even without this flag.
        # 256x256 avoids potential minimum-resolution limits on some encoder implementations.
        base_cmd = [
            ffmpeg_path, "-y", "-f", "lavfi", "-i", "color=c=black:s=256x256",
            "-frames:v", "1", "-pix_fmt", "yuv420p", "-c:v", enc,
        ]

        if enc.endswith("_nvenc"):
            # NVIDIA: try without -gpu flag first (works on most modern drivers),
            # then retry with -gpu 0 (sometimes needed on multi-GPU / Optimus setups).
            attempts = [
                base_cmd + [str(test_file)],
                base_cmd + ["-gpu", "0", str(test_file)],
            ]
        else:
            attempts = [base_cmd + [str(test_file)]]

        for cmd in attempts:
            ok, err = _try_encoder(ffmpeg_path, enc, cmd, test_file)
            if ok:
                logger.info(f"✓ Hardware encoder detected: {enc}")
                return enc
            logger.info(f"✗ {enc} unavailable: {err[:200] if err else 'unknown error'}")

    logger.warning(f"No GPU encoder available. Falling back to CPU: {cpu_encoder}")
    return cpu_encoder

def estimate_concurrent_encodes(best_encoder: str) -> int:
    """Estimate optimal number of concurrent encodes based on GPU/CPU."""
    if best_encoder.endswith("_nvenc"):
        # NVIDIA GPU: typically support 2-4 concurrent encodes
        return 3
    elif best_encoder.endswith("_qsv"):
        # Intel QSV: typically support 1-2 concurrent encodes
        return 2
    elif best_encoder.endswith("_amf"):
        # AMD AMF: typically support 1-2 concurrent encodes
        return 2
    else:
        # CPU fallback: limit to 1 to avoid system overload
        return 1

class VideoConverterConfig:
    def __init__(
        self,
        input_folder: Path,
        output_folder: Path,
        max_width: int,
        max_height: int,
        codec: str = "h264",
        encoder: Optional[str] = None,      # Pre-detected encoder; None = auto-detect at runtime
        quality: int = 18,                  # CQ/CRF value: 18=고화질, 23=균형, 28=용량 절약
        audio_bitrate: str = "256k",        # AAC audio bitrate: "128k", "192k", "256k"
        duplicate_handling: str = "skip",   # "skip" | "overwrite" | "rename"
        max_concurrent_encodes: int = 0,    # 0 = auto (determined by encoder type)
        error_log_lines: int = DEFAULT_GPU_ERROR_LOG_LINES
    ):
        self.input_folder = input_folder
        self.output_folder = output_folder
        self.max_width = max_width
        self.max_height = max_height
        self.codec = codec
        self.encoder = encoder
        self.quality = quality
        self.audio_bitrate = audio_bitrate
        self.duplicate_handling = duplicate_handling
        self.max_concurrent_encodes = max_concurrent_encodes
        self.error_log_lines = error_log_lines

class VideoConverterResult:
    def __init__(self):
        self.success = 0
        self.skipped = 0
        self.failed = 0
        self.cancelled = False

def _resolve_output_path(
    original_path: Path,
    output_folder: Path,
    max_attempts: int = DEFAULT_FILENAME_CONFLICT_ATTEMPTS,
    reserved_paths: Optional[set] = None,
) -> Path:
    """Resolve output path, handling filename conflicts."""
    out_path = output_folder / original_path.name
    reserved_paths = reserved_paths if reserved_paths is not None else set()
    if not out_path.exists() and out_path not in reserved_paths:
        return out_path
    
    for idx in range(1, max_attempts):
        out_path = output_folder / f"{original_path.stem}_{idx}{original_path.suffix}"
        if not out_path.exists() and out_path not in reserved_paths:
            return out_path
    
    logger.warning(f"Exceeded {max_attempts} attempts to find unique filename for {original_path.name}")
    return output_folder / f"{original_path.stem}_{max_attempts}{original_path.suffix}"

def _get_hwaccel_args(encoder: str) -> list:
    """Return FFmpeg hardware-accelerated decode arguments for the given encoder.

    Strategy: pair the hardware decoder with its matching encoder to avoid
    cross-device frame transfers. Frames are decoded on GPU and automatically
    transferred to system memory before the (CPU) scale filter runs, then the
    matching GPU encoder picks them up. FFmpeg auto-falls back to software
    decode if the source codec is not supported by the hardware decoder.

    - NVENC → NVDEC  (-hwaccel cuda)
    - QSV   → QSV    (-hwaccel qsv)
    - AMF   → D3D11VA (-hwaccel d3d11va, Windows-only, works with AMD/Intel/NVIDIA)
    - CPU   → no hwaccel (unnecessary overhead)
    """
    if encoder.endswith("_nvenc"):
        return ["-hwaccel", "cuda"]
    elif encoder.endswith("_qsv"):
        return ["-hwaccel", "qsv"]
    elif encoder.endswith("_amf"):
        return ["-hwaccel", "d3d11va"]
    return []


def _run_encode_pass(
    ffmpeg_path: str,
    file_path: Path,
    out_path: Path,
    encoder: str,
    scale_filter: str,
    duration: float,
    task_progress_cb: Callable = None,
    task_number: int = 0,
    stats: ThreadSafeStats = None,
    cancel_flag: threading.Event = None,
    error_log_lines: int = DEFAULT_GPU_ERROR_LOG_LINES,
    worker_context = None,
    quality: int = 18,
    audio_bitrate: str = "256k",
) -> tuple[int, str]:
    """
    Run a single encoding pass and return (return_code, error_log).
    """
    enc_args = EncoderConfig.get_encoder_args(encoder, quality)
    hwaccel_args = _get_hwaccel_args(encoder)
    cmd_ffmpeg = [
        ffmpeg_path, "-y",
    ] + hwaccel_args + [
        "-i", str(file_path),
        "-map", "0:v:0", "-map", "0:a?", "-vf", scale_filter,
    ] + enc_args + [
        "-c:a", "aac", "-b:a", audio_bitrate,
        "-sn", "-dn",
        "-map_metadata", "0", "-movflags", "use_metadata_tags",
        str(out_path)
    ]
    
    process = subprocess.Popen(
        cmd_ffmpeg, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        universal_newlines=True, creationflags=SUBPROCESS_FLAGS,
        encoding='utf-8', errors='replace'
    )
    
    if worker_context and hasattr(worker_context, "register_process"):
        worker_context.register_process(process)
    elif worker_context:
        worker_context.active_process = process
    
    err_log = []
    
    try:
        while True:
            if cancel_flag and cancel_flag.is_set():
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                break
            
            line = process.stderr.readline()
            if not line and process.poll() is not None:
                break
            
            if line:
                err_log.append(line)
                if "time=" in line and duration > 0:
                    parts = line.split("time=")
                    if len(parts) > 1:
                        curr_time = _parse_ffmpeg_time(parts[1].split()[0])
                        pct = min((curr_time / duration) * 100, 100)
                        # Use task_progress_cb if available (for per-task progress)
                        if task_progress_cb and task_number > 0:
                            task_progress_cb(task_number, file_path.name, pct)
                        # Also update overall stats
                        if stats:
                            stats.set("_current_pct", pct)
    finally:
        if worker_context and hasattr(worker_context, "unregister_process"):
            worker_context.unregister_process(process)
        elif worker_context:
            worker_context.active_process = None
    
    retcode = process.poll() if process.poll() is not None else -1
    log_str = "".join(err_log[-error_log_lines:]) if err_log else ""
    return retcode, log_str

def run_video_conversion(
    config: VideoConverterConfig,
    progress_cb: Callable[[str, int, int, dict], None] = None,
    task_progress_cb: Callable[[int, str, float], None] = None,
    task_finished_cb: Callable[[int, str], None] = None,
    max_concurrent_cb: Callable[[int], None] = None,
    cancel_flag: threading.Event = None,
    worker_context=None
) -> VideoConverterResult:
    """
    Run video conversion with parallel encoding support for GPU acceleration.
    """
    result = VideoConverterResult()
    stats = ThreadSafeStats()
    
    ffmpeg_path = resolve_ffmpeg_path()
    ffprobe_path = resolve_ffprobe_path()

    if progress_cb:
        progress_cb("Scanning videos...", 0, 0, stats.get_all())
    
    # Collect all video files
    all_files = []
    for root, dirs, files in os.walk(config.input_folder):
        for f in files:
            p = Path(root) / f
            if p.suffix.lower() in VIDEO_EXTENSIONS:
                all_files.append(p)
    
    total_files = len(all_files)
    config.output_folder.mkdir(parents=True, exist_ok=True)
    failed_folder = config.output_folder / "_Failed_Conversions"

    # Use encoder cached from the setup screen if available; otherwise detect now.
    if config.encoder:
        best_encoder = config.encoder
        logger.info(f"Using pre-detected encoder: {best_encoder}")
        if progress_cb:
            progress_cb(f"Using {best_encoder}...", total_files, total_files, stats.get_all())
    else:
        if progress_cb:
            progress_cb("Detecting GPU Acceleration...", total_files, total_files, stats.get_all())
        best_encoder = detect_hardware_encoder(ffmpeg_path, config.output_folder, config.codec)
    cpu_fallback_encoder = "libx265" if config.codec == "hevc" else "libx264"
    
    # Estimate concurrent encodes based on GPU capability
    estimated_max_concurrent = estimate_concurrent_encodes(best_encoder)
    if config.max_concurrent_encodes <= 0:
        # 0 = auto: let encoder type decide
        max_concurrent = estimated_max_concurrent
    else:
        max_concurrent = min(config.max_concurrent_encodes, estimated_max_concurrent)
    logger.info(f"Using {best_encoder}. Max concurrent encodes: {max_concurrent} (requested={config.max_concurrent_encodes or 'auto'})")
    
    # Notify GUI of max concurrent
    if max_concurrent_cb:
        max_concurrent_cb(max_concurrent)
    
    # Files that need conversion
    files_to_convert = []
    convert_count = 0  # Track actual conversions
    
    for i, file_path in enumerate(all_files):
        if cancel_flag and cancel_flag.is_set():
            result.cancelled = True
            break
        
        w, h = get_video_resolution(ffprobe_path, file_path)
        
        if w == 0 or h == 0:
            logger.info(f"Skipping {file_path.name}: Could not read resolution.")
            stats.increment("skipped")
            continue
        
        # Only convert if resolution exceeds limits
        if w > config.max_width or h > config.max_height:
            # --- Duplicate handling ---
            tentative_out = config.output_folder / file_path.name
            if tentative_out.exists():
                if config.duplicate_handling == "skip":
                    logger.info(f"Skipping {file_path.name}: output already exists (duplicate skip)")
                    stats.increment("skipped")
                    continue
                elif config.duplicate_handling == "overwrite":
                    logger.info(f"Overwriting existing output for {file_path.name}")
                # "rename" falls through — _resolve_output_path will add suffix

            files_to_convert.append((convert_count, file_path, w, h))
            convert_count += 1
        else:
            logger.info(f"Skipping {file_path.name} (Resolution: {w}x{h}, within target)")
            stats.increment("skipped")
    
    if result.cancelled:
        result.success = stats.get("success", 0)
        result.skipped = stats.get("skipped", 0)
        result.failed = stats.get("failed", 0)
        return result
    
    # Notify about conversion queue size
    total_to_convert = len(files_to_convert)
    if progress_cb:
        progress_cb(f"Starting conversion of {total_to_convert} files...", 0, total_to_convert, stats.get_all())
    
    # GUI slot queue: each slot corresponds to a task bar in the progress screen.
    # Tasks acquire a slot when they start and release it when done,
    # so slot numbers always stay within 1..max_concurrent regardless of
    # how many total files there are.
    slot_queue: Queue = Queue()
    for _s in range(1, max_concurrent + 1):
        slot_queue.put(_s)

    # Parallel conversion using ThreadPoolExecutor
    reserved_output_paths = set()
    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        futures_to_index = {}
        completed_count = 0

        for idx, (convert_idx, file_path, w, h) in enumerate(files_to_convert):
            if cancel_flag and cancel_flag.is_set():
                result.cancelled = True
                break

            # Resolve output path based on duplicate_handling setting
            if config.duplicate_handling == "overwrite":
                out_path = config.output_folder / file_path.name
            else:
                out_path = _resolve_output_path(
                    file_path,
                    config.output_folder,
                    reserved_paths=reserved_output_paths,
                )
            reserved_output_paths.add(out_path)

            scale_filter = f"scale={config.max_width}:{config.max_height}:force_original_aspect_ratio=decrease"
            duration = get_video_duration(ffprobe_path, file_path)

            logger.info(f"[Task {idx+1}/{total_to_convert}] Queuing {file_path.name} → {out_path.name} via {best_encoder}")

            future = executor.submit(
                _convert_video_task,
                ffmpeg_path,
                file_path,
                out_path,
                best_encoder,
                cpu_fallback_encoder,
                scale_filter,
                duration,
                task_progress_cb,
                task_finished_cb,
                stats,
                cancel_flag,
                config.error_log_lines,
                worker_context,
                failed_folder,
                idx + 1,            # sequential index for logging
                total_to_convert,
                slot_queue,         # GUI slot pool
                config.quality,
                config.audio_bitrate,
            )
            futures_to_index[future] = (idx + 1, file_path.name)
        
        # Wait for all futures to complete
        for future in as_completed(futures_to_index):
            if cancel_flag and cancel_flag.is_set():
                result.cancelled = True
                break
            try:
                future.result()
                completed_count += 1
                # Update overall progress bar
                if progress_cb:
                    progress_cb(f"Converting files... ({completed_count}/{total_to_convert})", completed_count, total_to_convert, stats.get_all())
            except Exception as e:
                logger.error(f"Task execution error: {e}")

    result.success = stats.get("success", 0)
    result.skipped = stats.get("skipped", 0)
    result.failed = stats.get("failed", 0)
    
    return result

def _convert_video_task(
    ffmpeg_path: str,
    file_path: Path,
    out_path: Path,
    best_encoder: str,
    cpu_fallback_encoder: str,
    scale_filter: str,
    duration: float,
    task_progress_cb: Callable,
    task_finished_cb: Callable,
    stats: ThreadSafeStats,
    cancel_flag: threading.Event,
    error_log_lines: int,
    worker_context,
    failed_folder: Path,
    task_number: int,   # sequential index for logging (1-based)
    total_tasks: int,
    slot_queue: Queue,  # GUI slot pool (1..max_concurrent)
    quality: int = 18,
    audio_bitrate: str = "256k",
) -> None:
    """
    Task function for parallel video conversion.
    Acquires a GUI slot from slot_queue at start, releases it when done
    so slot numbers never exceed max_concurrent regardless of total file count.
    """
    if cancel_flag and cancel_flag.is_set():
        return

    gui_slot = slot_queue.get()
    try:
        logger.info(f"[Task {task_number}/{total_tasks}] Starting: {file_path.name}")
        if task_progress_cb:
            task_progress_cb(gui_slot, file_path.name, 0.0)

        retcode, log_str = _run_encode_pass(
            ffmpeg_path, file_path, out_path,
            best_encoder, scale_filter, duration,
            task_progress_cb, gui_slot,
            stats, cancel_flag, error_log_lines, worker_context,
            quality, audio_bitrate,
        )

        if cancel_flag and cancel_flag.is_set():
            if out_path.exists():
                out_path.unlink()
            return

        # Fallback to CPU if GPU encoding failed
        if retcode != 0 and best_encoder != cpu_fallback_encoder:
            logger.warning(
                f"[Task {task_number}] GPU encoding failed (code {retcode}) for "
                f"{file_path.name}. Falling back to CPU."
            )
            if out_path.exists():
                out_path.unlink()
            retcode, log_str = _run_encode_pass(
                ffmpeg_path, file_path, out_path,
                cpu_fallback_encoder, scale_filter, duration,
                task_progress_cb, gui_slot,
                stats, cancel_flag, error_log_lines, worker_context,
                quality, audio_bitrate,
            )

        # Handle result
        if retcode != 0:
            logger.error(f"[Task {task_number}] Failed converting {file_path.name}. Exit Code: {retcode}")
            stats.increment("failed")
            failed_folder.mkdir(parents=True, exist_ok=True)
            with open(failed_folder / f"{file_path.name}_FAILED.txt", "w", encoding="utf-8") as err_f:
                err_f.write(f"Failed to convert: {file_path}\nExit Code: {retcode}\nFFmpeg Log:\n{log_str}")
            if out_path.exists():
                out_path.unlink()
        else:
            stats.increment("success")
            logger.info(f"[Task {task_number}] ✓ Successfully converted {file_path.name}")

        if task_finished_cb:
            task_finished_cb(gui_slot, file_path.name)
    finally:
        slot_queue.put(gui_slot)
