"""
Metadata extraction via ExifTool.
Uses -stay_open persistent process: single launch, no console flash per chunk.
Falls back to per-chunk subprocess if stay_open init fails.

All helpers are inlined here — no sys.path manipulation required.
"""
# -*- coding: utf-8 -*-
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Windows: suppress console window for every subprocess we spawn
_NO_WINDOW: int = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# ── Supported file extensions (kept in sync with exiftool_batch_to_mvp_csv.py) ──
SUPPORTED_EXTENSIONS = {
    ".arw", ".jpg", ".jpeg", ".png", ".heic", ".heif",
    ".dng", ".tif", ".tiff", ".webp",
    ".mov", ".mp4", ".m4v", ".avi", ".mkv", ".3gp",
}

# ── ExifTool tag flags ────────────────────────────────────────────────────────
_EXIFTOOL_FLAGS: List[str] = [
    "-j", "-n", "-m",
    "-charset", "filename=utf8",
    "-api", "LargeFileSupport=1",
    "-FileName", "-FileType", "-MIMEType", "-FileSize#",
    "-DateTimeOriginal", "-CreateDate", "-MediaCreateDate", "-TrackCreateDate",
    "-Copyright", "-ColorSpace", "-Make", "-Model",
    "-LensID", "-LensModel", "-Lens", "-FocalLength#",
    "-FNumber", "-ExposureTime", "-ISO", "-Flash", "-ShutterCount",
    "-ImageWidth", "-ImageHeight", "-Duration#",
    "-GPSLatitude#", "-GPSLongitude#", "-GPSAltitude#",
    "-QuickTime:GPSLatitude#", "-QuickTime:GPSLongitude#", "-QuickTime:GPSAltitude#",
    "-Keys:GPSCoordinates",
]


# ── Inlined helpers (duplicated from exiftool_batch_to_mvp_csv.py) ────────────

def _to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.8f}".rstrip("0").rstrip(".")
    return str(value)


def _first_present(record: Dict[str, Any], keys: List[str]) -> Optional[Any]:
    for k in keys:
        if k in record and record[k] not in ("", None):
            return record[k]
    return None


def _parse_quicktime_gps(raw: str) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    txt = raw.strip().replace(",", " ")
    parts = [p for p in txt.split() if p]
    if len(parts) < 2:
        return None, None, None
    try:
        lat = float(parts[0])
        lon = float(parts[1])
        alt = float(parts[2]) if len(parts) >= 3 else None
        return lat, lon, alt
    except ValueError:
        return None, None, None


def _hash_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as fp:
        while True:
            chunk = fp.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def list_files(scan_folder: Path, recursive: bool) -> List[Path]:
    if recursive:
        return [p for p in scan_folder.rglob("*") if p.is_file()]
    return [p for p in scan_folder.iterdir() if p.is_file()]


def make_error_row(path: Path, message: str) -> Dict[str, str]:
    return {
        "file_name": path.name,
        "file_type": path.suffix.lstrip(".").upper(),
        "mime_type": "",
        "file_size_bytes": str(path.stat().st_size) if path.exists() else "",
        "file_hash": "",
        "datetime_original": "",
        "copyright": "",
        "color_space": "",
        "device_make": "",
        "device_model": "",
        "lens": "",
        "focal_length_mm": "",
        "aperture": "",
        "exposure_time": "",
        "iso": "",
        "flash": "",
        "shutter_count": "",
        "image_width": "",
        "image_height": "",
        "duration_sec": "",
        "gps_lat": "",
        "gps_lon": "",
        "gps_alt": "",
        "geo_country": "",
        "geo_city": "",
        "target_folder": "",
        "sort_status": "Error",
        "error_message": message,
        "source_path": str(path),
    }


def _map_record(record: Dict[str, Any], compute_hash: bool) -> Dict[str, str]:
    source_path = Path(str(record.get("SourceFile", "")))

    gps_lat = _first_present(record, ["GPSLatitude", "QuickTime:GPSLatitude"])
    gps_lon = _first_present(record, ["GPSLongitude", "QuickTime:GPSLongitude"])
    gps_alt = _first_present(record, ["GPSAltitude", "QuickTime:GPSAltitude"])
    if (gps_lat in (None, "")) or (gps_lon in (None, "")):
        qt_raw = _first_present(record, ["Keys:GPSCoordinates"])
        if isinstance(qt_raw, str):
            q_lat, q_lon, q_alt = _parse_quicktime_gps(qt_raw)
            if q_lat is not None and q_lon is not None:
                gps_lat, gps_lon = q_lat, q_lon
                if gps_alt in (None, ""):
                    gps_alt = q_alt

    dt = _first_present(record, ["DateTimeOriginal", "CreateDate", "MediaCreateDate", "TrackCreateDate"])
    size = _first_present(record, ["FileSize"])
    if size in (None, "") and source_path.exists() and source_path.is_file():
        size = source_path.stat().st_size

    file_hash = ""
    if compute_hash and source_path.exists() and source_path.is_file():
        file_hash = _hash_file(source_path)

    return {
        "file_name": _to_str(_first_present(record, ["FileName"]) or source_path.name),
        "file_type": _to_str(_first_present(record, ["FileType"])),
        "mime_type": _to_str(_first_present(record, ["MIMEType"])),
        "file_size_bytes": _to_str(size),
        "file_hash": _to_str(file_hash),
        "datetime_original": _to_str(dt),
        "copyright": _to_str(_first_present(record, ["Copyright"])),
        "color_space": _to_str(_first_present(record, ["ColorSpace"])),
        "device_make": _to_str(_first_present(record, ["Make"])),
        "device_model": _to_str(_first_present(record, ["Model"])),
        "lens": _to_str(_first_present(record, ["LensModel", "Lens", "LensID"])),
        "focal_length_mm": _to_str(_first_present(record, ["FocalLength"])),
        "aperture": _to_str(_first_present(record, ["FNumber"])),
        "exposure_time": _to_str(_first_present(record, ["ExposureTime"])),
        "iso": _to_str(_first_present(record, ["ISO"])),
        "flash": _to_str(_first_present(record, ["Flash"])),
        "shutter_count": _to_str(_first_present(record, ["ShutterCount"])),
        "image_width": _to_str(_first_present(record, ["ImageWidth"])),
        "image_height": _to_str(_first_present(record, ["ImageHeight"])),
        "duration_sec": _to_str(_first_present(record, ["Duration"])),
        "gps_lat": _to_str(gps_lat),
        "gps_lon": _to_str(gps_lon),
        "gps_alt": _to_str(gps_alt),
        "geo_country": "",
        "geo_city": "",
        "target_folder": "",
        "sort_status": "Pending",
        "error_message": "",
        "source_path": _to_str(source_path),
    }


# ── Stay-open ExifTool process ────────────────────────────────────────────────

class _StayOpenExifTool:
    """Single persistent ExifTool process (-stay_open mode).

    Eliminates per-chunk subprocess spawning → no console flash, faster throughput.
    """

    def __init__(self, exiftool_path: str) -> None:
        self._path = exiftool_path
        self._proc: Optional[subprocess.Popen] = None

    def __enter__(self) -> "_StayOpenExifTool":
        self._proc = subprocess.Popen(
            [self._path, "-stay_open", "True", "-@", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            encoding="utf-8",
            creationflags=_NO_WINDOW,
        )
        return self

    def __exit__(self, *_) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.stdin.write("-stay_open\nFalse\n")
                self._proc.stdin.flush()
                self._proc.stdin.close()
            except OSError:
                pass
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None

    def execute(self, files: List[Path]) -> List[Dict[str, Any]]:
        if self._proc is None or self._proc.poll() is not None:
            raise RuntimeError("ExifTool process is not running")

        cmd_lines = _EXIFTOOL_FLAGS + [str(f) for f in files] + ["-execute"]
        self._proc.stdin.write("\n".join(cmd_lines) + "\n")
        self._proc.stdin.flush()

        out_lines: List[str] = []
        while True:
            line = self._proc.stdout.readline()
            if not line:
                raise RuntimeError("ExifTool process closed unexpectedly")
            if line.rstrip("\r\n") == "{ready}":
                break
            out_lines.append(line)

        raw = "".join(out_lines).strip()
        if not raw:
            return []
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("ExifTool JSON parse error") from exc
        if not isinstance(payload, list):
            raise RuntimeError("Unexpected ExifTool output format")
        return payload


def _run_chunk_fallback(exiftool_path: str, files: List[Path]) -> List[Dict[str, Any]]:
    """One-shot subprocess per chunk. CREATE_NO_WINDOW prevents flash."""
    cmd = [exiftool_path] + _EXIFTOOL_FLAGS + [str(f) for f in files]
    try:
        result = subprocess.run(
            cmd, check=True, capture_output=True,
            text=True, encoding="utf-8", creationflags=_NO_WINDOW,
        )
    except FileNotFoundError as exc:
        raise FileNotFoundError("ExifTool executable not found") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ExifTool error: {(exc.stderr or '').strip()}") from exc
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("ExifTool JSON parse error") from exc
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected ExifTool output format")
    return payload


# ── Public API ────────────────────────────────────────────────────────────────

def extract_metadata(
    scan_folder: Path,
    exiftool_path: str,
    recursive: bool = True,
    compute_hash: bool = False,
    chunk_size: int = 300,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> List[dict]:
    """Extract EXIF metadata using a single persistent ExifTool process.

    progress_cb(done, total) called after each chunk.
    """
    all_files = list_files(scan_folder=scan_folder, recursive=recursive)
    supported_files: List[Path] = []
    rows: List[dict] = []

    for path in all_files:
        ext = path.suffix.lower()
        if ext and ext not in SUPPORTED_EXTENSIONS:
            rows.append(make_error_row(path, "Unsupported extension"))
        elif not ext:
            rows.append(make_error_row(path, "Missing file extension"))
        else:
            supported_files.append(path)

    total = len(supported_files)
    if progress_cb:
        progress_cb(0, total)

    if not supported_files:
        return rows

    raw_records: List[Dict[str, Any]] = []
    use_fallback = False

    try:
        with _StayOpenExifTool(exiftool_path) as et:
            done = 0
            for i in range(0, total, chunk_size):
                chunk = supported_files[i : i + chunk_size]
                raw_records.extend(et.execute(chunk))
                done += len(chunk)
                if progress_cb:
                    progress_cb(done, total)
    except FileNotFoundError:
        raise
    except Exception:
        use_fallback = True

    if use_fallback:
        raw_records.clear()
        done = 0
        for i in range(0, total, chunk_size):
            chunk = supported_files[i : i + chunk_size]
            raw_records.extend(_run_chunk_fallback(exiftool_path, chunk))
            done += len(chunk)
            if progress_cb:
                progress_cb(done, total)

    mapped = [_map_record(r, compute_hash=compute_hash) for r in raw_records]
    mapped_by_source = {str(Path(r.get("source_path", ""))): r for r in mapped}

    for path in supported_files:
        key = str(path)
        if key in mapped_by_source:
            rows.append(mapped_by_source[key])
        else:
            rows.append(make_error_row(path, "ExifTool read failed"))

    return rows


def resolve_exiftool_path(extra_candidates: Optional[List[str]] = None) -> Optional[str]:
    """Find ExifTool executable. Returns path string or None if not found."""
    import shutil

    candidates: List[str] = []

    # 1. Next to this executable (Nuitka standalone: assets/ is in exe dir)
    exe_dir = Path(sys.executable).parent
    candidates.append(str(exe_dir / "assets" / "exiftool.exe"))
    candidates.append(str(exe_dir / "exiftool.exe"))

    # 2. assets/ relative to project root (dev environment)
    project_root = Path(__file__).parent.parent
    candidates.append(str(project_root / "assets" / "exiftool.exe"))

    # 3. Extra candidates from caller
    if extra_candidates:
        candidates.extend(extra_candidates)

    # 4. PATH
    candidates.append("exiftool")

    # 5. Known local install location
    candidates.append(
        r"c:\Users\user\Downloads\exiftool-13.55_64\exiftool-13.55_64\exiftool.exe"
    )

    for candidate in candidates:
        if candidate.lower() in ("exiftool", "exiftool.exe"):
            if shutil.which(candidate):
                return candidate
            continue
        if Path(candidate).exists():
            return candidate

    return None
