"""
Country/city classification.
Wraps country_classification_mvp.py functions with a progress callback interface.

Import strategy: country_classification_mvp.py lives at the project root (legacy CLI script).
We add the root to sys.path so it can be imported as a top-level module.
Nuitka resolves this statically at compile time — the path manipulation is a dev-environment
convenience only. If you move this package out of the project tree, refactor the functions here.
"""
import sys
from importlib.util import find_spec
from pathlib import Path
from typing import Callable, List, Optional

# Ensure project root is on the path so Nuitka/dev both find country_classification_mvp
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

if find_spec("country_classification_mvp") is None:
    raise ImportError(
        "country_classification_mvp not found. "
        f"Expected at: {_PROJECT_ROOT}/country_classification_mvp.py"
    )

from country_classification_mvp import (  # noqa: E402
    classify_rows,
    load_city_index,
    load_south_america_polygons,
    mark_duplicates,
    write_sqlite,
)


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
    """Classify rows by country/city using Natural Earth shapefiles.

    progress_cb(done, total) called once classification is complete (single-pass).
    Returns enriched rows with geo_country, geo_city, target_folder, sort_status filled in.
    """
    polygons = load_south_america_polygons(shapefile_path)
    if not polygons:
        raise RuntimeError(f"No South America polygons found in shapefile: {shapefile_path}")

    city_index = load_city_index(cities_csv)

    total = len(rows)
    if progress_cb:
        progress_cb(0, total)

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
        mark_duplicates(enriched, db_path)

    if progress_cb:
        progress_cb(total, total)

    if db_path:
        write_sqlite(db_path, enriched)

    return enriched
