"""
Metadata extraction via ExifTool.
Wraps exiftool_batch_to_mvp_csv.py functions with a progress callback interface.
"""
import sys
from pathlib import Path
from typing import Callable, List, Optional

# Re-use all logic from the existing script
sys.path.insert(0, str(Path(__file__).parent.parent))
from exiftool_batch_to_mvp_csv import (
    SUPPORTED_EXTENSIONS,
    build_exiftool_command,
    hash_file,
    list_files,
    make_error_row,
    map_record,
    run_exiftool,
)


def extract_metadata(
    scan_folder: Path,
    exiftool_path: str,
    recursive: bool = True,
    compute_hash: bool = False,
    chunk_size: int = 300,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> List[dict]:
    """Extract EXIF metadata from all supported files in scan_folder.

    progress_cb(done, total) called after each ExifTool chunk.
    Returns list of row dicts matching SCHEMA_COLUMNS from the exiftool script.
    """
    all_files = list_files(scan_folder=scan_folder, recursive=recursive)
    supported_files: List[Path] = []
    rows: List[dict] = []

    for path in all_files:
        ext = path.suffix.lower()
        if ext and ext not in SUPPORTED_EXTENSIONS:
            rows.append(make_error_row(path, "Unsupported extension"))
            continue
        if not ext:
            rows.append(make_error_row(path, "Missing file extension"))
            continue
        supported_files.append(path)

    total = len(supported_files)
    done = 0

    raw_records: List[dict] = []
    for i in range(0, total, chunk_size):
        chunk = supported_files[i : i + chunk_size]
        cmd = build_exiftool_command(exiftool_path=exiftool_path, files=chunk)
        raw_records.extend(run_exiftool(cmd))
        done += len(chunk)
        if progress_cb:
            progress_cb(done, total)

    mapped = [map_record(record, compute_hash=compute_hash) for record in raw_records]
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

    # 1. Next to this executable (for Nuitka standalone)
    exe_dir = Path(sys.executable).parent
    candidates.append(str(exe_dir / "exiftool.exe"))

    # 2. assets/ relative to project root
    project_root = Path(__file__).parent.parent
    candidates.append(str(project_root / "assets" / "exiftool.exe"))

    # 3. Extra candidates from caller
    if extra_candidates:
        candidates.extend(extra_candidates)

    # 4. PATH
    candidates.append("exiftool")

    # 5. Known install location
    candidates.append(r"c:\Users\user\Downloads\exiftool-13.55_64\exiftool-13.55_64\exiftool.exe")

    for candidate in candidates:
        if candidate.lower() in ("exiftool", "exiftool.exe"):
            if shutil.which(candidate):
                return candidate
            continue
        if Path(candidate).exists():
            return candidate

    return None
