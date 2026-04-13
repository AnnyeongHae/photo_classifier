"""
Full pipeline orchestrator: Extract -> Classify -> Move.
Used by the QThread worker and can also be called directly.
"""
# -*- coding: utf-8 -*-
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from core.extractor import extract_metadata, resolve_exiftool_path
from core.classifier import classify_files
from core.mover import move_files, MoveStats
from core.logging_config import get_logger

logger = get_logger(__name__)


STEP_EXTRACT = "extract"
STEP_CLASSIFY = "classify"
STEP_MOVE = "move"


@dataclass
class PipelineConfig:
    input_folder: Path
    output_folder: Path
    exiftool_path: str
    assets_dir: Path
    db_path: Path
    duplicate_policy: str = "rename"
    max_city_distance_km: float = 30.0
    fallback_city: str = "Unknown_City"
    folder_depth: str = "city" # 'country', 'city', 'date', 'country_date'
    no_gps_depth: str = "date" # 'date', 'date_model'
    only_success_files: bool = False


@dataclass
class PipelineResult:
    rows: List[dict] = field(default_factory=list)
    move_stats: Optional[MoveStats] = None
    cancelled: bool = False
    error: Optional[str] = None

    @property
    def total(self) -> int:
        return len(self.rows)

    @property
    def success(self) -> int:
        return sum(1 for r in self.rows if r.get("sort_status") in ("Success", "Success_Country_Others"))

    @property
    def no_gps(self) -> int:
        return sum(1 for r in self.rows if r.get("sort_status") == "No_GPS")

    @property
    def other_regions(self) -> int:
        return sum(1 for r in self.rows if r.get("sort_status") == "Other_Regions")

    @property
    def duplicates(self) -> int:
        return sum(1 for r in self.rows if r.get("is_duplicate") == "yes")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.rows if r.get("sort_status") == "Error")

    @property
    def moved(self) -> int:
        return self.move_stats.verified if self.move_stats else 0

    @property
    def move_failed(self) -> int:
        return self.move_stats.failed if self.move_stats else 0

    @property
    def move_skipped(self) -> int:
        return (self.move_stats.skipped_duplicate + self.move_stats.skipped_missing) if self.move_stats else 0

    @property
    def move_renamed(self) -> int:
        return self.move_stats.renamed if self.move_stats else 0


from typing import Any
ProgressCb = Optional[Callable[..., None]]
# (step_name, done, total, stats_dict)


def run_full_pipeline(
    config: PipelineConfig,
    progress_cb: ProgressCb = None,
    cancel_flag: Optional[threading.Event] = None,
) -> PipelineResult:
    """Run the full 3-step pipeline with optional progress callbacks.

    Raises RuntimeError on cancellation.
    Returns PipelineResult with all rows and move stats.
    """
    try:
        logger.info("Starting pipeline...")
        logger.info(f"  Input: {config.input_folder}")
        logger.info(f"  Output: {config.output_folder}")
        logger.info(f"  Policy: {config.duplicate_policy}")
        
        shapefile_path = config.assets_dir / "Natural Earth_10m_admin_0_countries" / "ne_10m_admin_0_countries.shp"
        cities_csv = config.assets_dir / "my_cities.csv"

        if not config.input_folder.exists():
            raise FileNotFoundError(f"Input folder not found: {config.input_folder}")
        if not shapefile_path.exists():
            raise FileNotFoundError(f"Shapefile not found: {shapefile_path}")

        result = PipelineResult()

        # ── Step 1: Extract ──────────────────────────────────────────────────────
        def extract_cb(done: int, total: int) -> None:
            if cancel_flag and cancel_flag.is_set():
                raise RuntimeError("Pipeline cancelled by user")
            if progress_cb:
                progress_cb(STEP_EXTRACT, done, total)

        logger.info("Step 1/3: Extracting metadata...")
        rows = extract_metadata(
            scan_folder=config.input_folder,
            exiftool_path=config.exiftool_path,
            recursive=True,
            progress_cb=extract_cb,
        )
        logger.info(f"Extracted metadata from {len(rows)} files")

        if cancel_flag and cancel_flag.is_set():
            logger.warning("Pipeline cancelled during extraction")
            result.cancelled = True
            return result

        # ── Step 2: Classify ─────────────────────────────────────────────────────
        def classify_cb(done: int, total: int) -> None:
            if cancel_flag and cancel_flag.is_set():
                raise RuntimeError("Pipeline cancelled by user")
            if progress_cb:
                progress_cb(STEP_CLASSIFY, done, total, None)

        logger.info("Step 2/3: Classifying files...")
        enriched = classify_files(
            rows=rows,
            shapefile_path=shapefile_path,
            cities_csv=cities_csv,
            target_root=str(config.output_folder),
            max_city_distance_km=config.max_city_distance_km,
            fallback_city=config.fallback_city,
            folder_depth=config.folder_depth,
            no_gps_depth=config.no_gps_depth,
            db_path=config.db_path,
            progress_cb=classify_cb,
        )
        result.rows = enriched
        logger.info(f"Classified {len(enriched)} files")

        if cancel_flag and cancel_flag.is_set():
            logger.warning("Pipeline cancelled during classification")
            result.cancelled = True
            return result

        # ── Step 3: Move ─────────────────────────────────────────────────────────
        def move_cb(done: int, total: int, stats: MoveStats) -> None:
            if progress_cb:
                stats_payload = {
                    "success": stats.success,
                    "duplicates": stats.skipped_duplicate + stats.renamed + stats.overwritten,
                    "skipped": stats.skipped_missing,
                    "failed": stats.failed_verify
                }
                progress_cb(STEP_MOVE, done, total, stats_payload)

        logger.info("Step 3/3: Moving files...")
        move_stats = move_files(
            rows=enriched,
            duplicate_policy=config.duplicate_policy,
            only_success=config.only_success_files,
            cancel_flag=cancel_flag,
            progress_cb=move_cb,
        )
        result.move_stats = move_stats
        
        import csv
        from collections import defaultdict
        from datetime import datetime

        date_str = datetime.now().strftime("%Y.%m.%d")

        # Split rows by category: date_{no_gps} / date_{country}
        category_rows: dict = defaultdict(list)
        for row in enriched:
            status = row.get("sort_status", "")
            if status == "No_GPS":
                category = "No_GPS"
            elif status == "Invalid_GPS":
                category = "Invalid_GPS"
            else:
                country = (row.get("geo_country") or "").strip()
                category = country.replace(" ", "_").replace("/", "_") if country else "Unknown"
            category_rows[category].append(row)

        try:
            from core.mvp import SCHEMA_COLUMNS
            for category, cat_rows in category_rows.items():
                csv_name = f"{date_str}_{category}.csv"
                cat_csv = config.db_path.parent / csv_name
                file_exists = cat_csv.exists() and cat_csv.stat().st_size > 0
                with cat_csv.open("a", encoding="utf-8-sig", newline="") as fp:
                    writer = csv.DictWriter(fp, fieldnames=SCHEMA_COLUMNS, extrasaction='ignore')
                    if not file_exists:
                        writer.writeheader()
                    writer.writerows(cat_rows)
                logger.info(f"Wrote {len(cat_rows)} rows to {cat_csv}")
        except Exception as e:
            logger.error(f"Failed to write category reports: {e}")

        # Write error report if there are any failures in extraction or moving
        failed_rows = [r for r in enriched if r.get("sort_status") == "Error" or "error_message" in r and r.get("error_message")]
        
        if failed_rows:
            error_csv = config.db_path.parent / f"{timestamp}_error_report.csv"
            keys = ["file_name", "sort_status", "error_message", "source_path"]
            try:
                with error_csv.open("w", encoding="utf-8-sig", newline="") as fp:
                    writer = csv.DictWriter(fp, fieldnames=keys, extrasaction='ignore')
                    writer.writeheader()
                    writer.writerows(failed_rows)
                logger.info(f"Wrote {len(failed_rows)} errors to {error_csv}")
            except Exception as e:
                logger.error(f"Failed to write error report: {e}")

        logger.info(f"Pipeline completed successfully! Moved {move_stats.verified} files")

        return result
    
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        result.error = str(e)
        raise
