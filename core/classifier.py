"""
Country/city classification.
Wraps core.mvp functions with a progress callback interface.
"""
# -*- coding: utf-8 -*-
from pathlib import Path
from typing import Callable, List, Optional

from core.logging_config import get_logger
from core.mvp import (
    classify_rows,
    load_city_index,
    load_south_america_polygons,
    mark_duplicates,
    write_sqlite,
)

logger = get_logger(__name__)


def classify_files(
    rows: List[dict],
    shapefile_path: Path,
    cities_csv: Path,
    target_root: str,
    max_city_distance_km: float = 30.0,
    fallback_city: str = "Unknown_City",
    db_path: Optional[Path] = None,
    compute_hash: bool = False,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> List[dict]:
    """Classify rows by country/city using Natural Earth shapefiles."""
    try:
        logger.debug(f"Loading polygons from {shapefile_path}")
        polygons = load_south_america_polygons(shapefile_path)
        if not polygons:
            raise RuntimeError(f"No South America polygons found in shapefile: {shapefile_path}")
        logger.info(f"Loaded {len(polygons)} polygons from shapefile")

        logger.debug(f"Loading city index from {cities_csv}")
        city_index = load_city_index(cities_csv)
        logger.info(f"Loaded city index with {len(city_index)} cities")

        total = len(rows)
        if progress_cb:
            progress_cb(0, total)

        logger.info(f"Classifying {total} rows...")
        enriched = classify_rows(
            rows=rows,
            polygons=polygons,
            city_index=city_index,
            lat_col="gps_lat",
            lon_col="gps_lon",
            target_root=target_root,
            compute_hash=compute_hash,
            max_city_distance_km=max_city_distance_km,
            fallback_city=fallback_city,
        )

        if db_path:
            logger.debug(f"Marking duplicates in {db_path}")
            mark_duplicates(enriched, db_path)

        if progress_cb:
            progress_cb(total, total)

        if db_path:
            logger.info(f"Writing {len(enriched)} rows to database: {db_path}")
            write_sqlite(db_path, enriched)

        logger.info("Classification completed successfully")
        return enriched
    
    except Exception as e:
        logger.error(f"Classification failed: {e}", exc_info=True)
        raise
