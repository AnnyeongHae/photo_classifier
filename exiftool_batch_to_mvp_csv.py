# -*- coding: utf-8 -*-
import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SCHEMA_COLUMNS = [
    "file_name",
    "file_type",
    "mime_type",
    "file_size_bytes",
    "file_hash",
    "datetime_original",
    "copyright",
    "color_space",
    "device_make",
    "device_model",
    "lens",
    "focal_length_mm",
    "aperture",
    "exposure_time",
    "iso",
    "flash",
    "shutter_count",
    "image_width",
    "image_height",
    "duration_sec",
    "gps_lat",
    "gps_lon",
    "gps_alt",
    "geo_country",
    "geo_city",
    "target_folder",
    "sort_status",
    "error_message",
    "source_path",
]

SUPPORTED_EXTENSIONS = {
    ".arw",
    ".jpg",
    ".jpeg",
    ".png",
    ".heic",
    ".heif",
    ".dng",
    ".tif",
    ".tiff",
    ".webp",
    ".mov",
    ".mp4",
    ".m4v",
    ".avi",
    ".mkv",
    ".3gp",
    ".osv",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch extract metadata via ExifTool and generate MVP input CSV."
    )
    parser.add_argument("--scan-folder", required=True, help="Folder to scan")
    parser.add_argument("--output-csv", default="metadata_input_from_exif.csv", help="Output CSV path")
    parser.add_argument(
        "--exiftool-path",
        default="exiftool",
        help="ExifTool executable path (e.g. exiftool or C:/tools/exiftool.exe)",
    )
    parser.add_argument("--no-recursive", action="store_true", help="Disable recursive scan")
    parser.add_argument("--compute-hash", action="store_true", help="Compute SHA1 file hashes (slower)")
    return parser.parse_args()


def to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.8f}".rstrip("0").rstrip(".")
    return str(value)


def first_present(record: Dict[str, Any], keys: List[str]) -> Optional[Any]:
    for k in keys:
        if k in record and record[k] not in ("", None):
            return record[k]
    return None


def parse_quicktime_gps_coordinates(raw: str) -> Tuple[Optional[float], Optional[float], Optional[float]]:
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


def hash_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as fp:
        while True:
            chunk = fp.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def build_exiftool_command(exiftool_path: str, files: List[Path]) -> List[str]:
    cmd = [
        exiftool_path,
        "-j",
        "-n",
        "-m",
        "-q",
        "-q",
        "-charset",
        "filename=utf8",
        "-api",
        "LargeFileSupport=1",
        "-FileName",
        "-FileType",
        "-MIMEType",
        "-FileSize#",
        "-DateTimeOriginal",
        "-CreateDate",
        "-MediaCreateDate",
        "-TrackCreateDate",
        "-Copyright",
        "-ColorSpace",
        "-Make",
        "-Model",
        "-LensID",
        "-LensModel",
        "-Lens",
        "-FocalLength#",
        "-FNumber",
        "-ExposureTime",
        "-ISO",
        "-Flash",
        "-ShutterCount",
        "-ImageWidth",
        "-ImageHeight",
        "-Duration#",
        "-GPSLatitude#",
        "-GPSLongitude#",
        "-GPSAltitude#",
        "-QuickTime:GPSLatitude#",
        "-QuickTime:GPSLongitude#",
        "-QuickTime:GPSAltitude#",
        "-Keys:GPSCoordinates",
    ]
    cmd.extend([str(p) for p in files])
    return cmd


def list_files(scan_folder: Path, recursive: bool) -> List[Path]:
    if recursive:
        return [p for p in scan_folder.rglob("*") if p.is_file()]
    return [p for p in scan_folder.iterdir() if p.is_file()]


def make_error_row(path: Path, message: str) -> Dict[str, str]:
    print(f"[ERROR] {message}: {path}")
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


def run_exiftool(cmd: List[str]) -> List[Dict[str, Any]]:
    try:
        completed = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            "ExifTool not found. Install it or pass --exiftool-path with full executable path."
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise RuntimeError(f"ExifTool failed: {stderr}") from exc
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Failed to decode ExifTool JSON output.") from exc
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected ExifTool output format.")
    return payload


def run_exiftool_in_chunks(exiftool_path: str, files: List[Path], chunk_size: int = 300) -> List[Dict[str, Any]]:
    all_rows: List[Dict[str, Any]] = []
    for i in range(0, len(files), chunk_size):
        chunk = files[i : i + chunk_size]
        cmd = build_exiftool_command(exiftool_path=exiftool_path, files=chunk)
        all_rows.extend(run_exiftool(cmd))
    return all_rows


def map_record(record: Dict[str, Any], compute_hash: bool) -> Dict[str, str]:
    source_path = Path(str(record.get("SourceFile", "")))

    gps_lat = first_present(record, ["GPSLatitude", "QuickTime:GPSLatitude"])
    gps_lon = first_present(record, ["GPSLongitude", "QuickTime:GPSLongitude"])
    gps_alt = first_present(record, ["GPSAltitude", "QuickTime:GPSAltitude"])
    if (gps_lat in (None, "")) or (gps_lon in (None, "")):
        qt_raw = first_present(record, ["Keys:GPSCoordinates"])
        if isinstance(qt_raw, str):
            q_lat, q_lon, q_alt = parse_quicktime_gps_coordinates(qt_raw)
            if q_lat is not None and q_lon is not None:
                gps_lat, gps_lon = q_lat, q_lon
                if gps_alt in (None, ""):
                    gps_alt = q_alt

    dt = first_present(record, ["DateTimeOriginal", "CreateDate", "MediaCreateDate", "TrackCreateDate"])

    size = first_present(record, ["FileSize"])
    if size in (None, "") and source_path.exists() and source_path.is_file():
        size = source_path.stat().st_size

    file_hash = ""
    if compute_hash and source_path.exists() and source_path.is_file():
        file_hash = hash_file(source_path)

    return {
        "file_name": to_str(first_present(record, ["FileName"]) or source_path.name),
        "file_type": to_str(first_present(record, ["FileType"])),
        "mime_type": to_str(first_present(record, ["MIMEType"])),
        "file_size_bytes": to_str(size),
        "file_hash": to_str(file_hash),
        "datetime_original": to_str(dt),
        "copyright": to_str(first_present(record, ["Copyright"])),
        "color_space": to_str(first_present(record, ["ColorSpace"])),
        "device_make": to_str(first_present(record, ["Make"])),
        "device_model": to_str(first_present(record, ["Model"])),
        "lens": to_str(first_present(record, ["LensModel", "Lens", "LensID"])),
        "focal_length_mm": to_str(first_present(record, ["FocalLength"])),
        "aperture": to_str(first_present(record, ["FNumber"])),
        "exposure_time": to_str(first_present(record, ["ExposureTime"])),
        "iso": to_str(first_present(record, ["ISO"])),
        "flash": to_str(first_present(record, ["Flash"])),
        "shutter_count": to_str(first_present(record, ["ShutterCount"])),
        "image_width": to_str(first_present(record, ["ImageWidth"])),
        "image_height": to_str(first_present(record, ["ImageHeight"])),
        "duration_sec": to_str(first_present(record, ["Duration"])),
        "gps_lat": to_str(gps_lat),
        "gps_lon": to_str(gps_lon),
        "gps_alt": to_str(gps_alt),
        "geo_country": "",
        "geo_city": "",
        "target_folder": "",
        "sort_status": "Pending",
        "error_message": "",
        "source_path": to_str(source_path),
    }


def write_csv(output_csv: Path, rows: List[Dict[str, str]]) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=SCHEMA_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    scan_folder = Path(args.scan_folder)
    if not scan_folder.exists() or not scan_folder.is_dir():
        raise FileNotFoundError(f"scan-folder does not exist: {scan_folder}")

    all_files = list_files(scan_folder=scan_folder, recursive=not args.no_recursive)
    supported_files: List[Path] = []
    rows: List[Dict[str, str]] = []

    for path in all_files:
        ext = path.suffix.lower()
        if ext and ext not in SUPPORTED_EXTENSIONS:
            rows.append(make_error_row(path, "Unsupported extension"))
            continue
        if not ext:
            rows.append(make_error_row(path, "Missing file extension"))
            continue
        supported_files.append(path)

    raw = run_exiftool_in_chunks(args.exiftool_path, supported_files) if supported_files else []
    mapped = [map_record(record, compute_hash=args.compute_hash) for record in raw]

    mapped_by_source = {str(Path(r.get("source_path", ""))): r for r in mapped}
    for path in supported_files:
        key = str(path)
        if key in mapped_by_source:
            rows.append(mapped_by_source[key])
        else:
            rows.append(make_error_row(path, "ExifTool read failed"))

    write_csv(Path(args.output_csv), rows)
    print(f"Done: {len(rows)} files -> {args.output_csv}")


if __name__ == "__main__":
    main()
