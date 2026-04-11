# -*- coding: utf-8 -*-
import argparse
import csv
import hashlib
import math
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import shapefile


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
    "orientation",
    "duration_sec",
    "gps_lat",
    "gps_lon",
    "gps_alt",
    "geo_country",
    "geo_city",
    "geo_city_ascii",
    "geo_city_distance_km",
    "target_folder",
    "sort_status",
    "unique_key",
    "is_duplicate",
    "duplicate_reason",
    "db_created_at",
    "db_updated_at",
]


@dataclass
class CountryPolygon:
    country_name: str
    iso_a2: str
    bbox: Tuple[float, float, float, float]
    rings: List[List[Tuple[float, float]]]


@dataclass
class CityPoint:
    name: str
    ascii_name: str
    lat: float
    lon: float
    country_code: str


def normalize_ascii(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.replace("/", "_").replace("\\", "_").strip()
    return "_".join(normalized.split()) if normalized else "Unknown"


def parse_date_folder(value: str) -> str:
    txt = (value or "").strip()
    if not txt:
        return "Unknown_Date"
    patterns = [
        "%Y:%m:%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y:%m:%d",
        "%Y-%m-%d",
    ]
    for fmt in patterns:
        try:
            dt = datetime.strptime(txt, fmt)
            return dt.strftime("%Y.%m.%d")
        except ValueError:
            continue
    # Fallback: pick leading date-like token when malformed
    token = txt.split(" ")[0].replace(":", ".").replace("-", ".")
    parts = token.split(".")
    if len(parts) >= 3 and all(p.isdigit() for p in parts[:3]):
        y, m, d = parts[0], parts[1].zfill(2), parts[2].zfill(2)
        if len(y) == 4:
            return f"{y}.{m}.{d}"
    return "Unknown_Date"





def partial_hash_file(path: Path, head_bytes: int = 64 * 1024) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as fp:
        digest.update(fp.read(head_bytes))
    return digest.hexdigest()


def build_unique_key(size_bytes: str, dt: str, partial_hash: str) -> str:
    raw = f"{size_bytes}|{dt}|{partial_hash}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def parse_float(value: str) -> Optional[float]:
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_int(value: str) -> Optional[int]:
    if value is None:
        return None
    txt = str(value).strip()
    if not txt:
        return None
    try:
        return int(float(txt))
    except ValueError:
        return None


def compute_orientation(width_value: str, height_value: str) -> str:
    w = parse_int(width_value)
    h = parse_int(height_value)
    if w is None or h is None:
        return "unknown"
    if w > h:
        return "landscape"
    if h > w:
        return "portrait"
    return "square"
    value = str(value).strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def point_in_ring(x: float, y: float, ring: List[Tuple[float, float]]) -> bool:
    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) if (yj - yi) != 0 else 1e-12) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def point_in_country(x: float, y: float, country: CountryPolygon) -> bool:
    min_x, min_y, max_x, max_y = country.bbox
    if x < min_x or x > max_x or y < min_y or y > max_y:
        return False
    inside = False
    for ring in country.rings:
        if point_in_ring(x, y, ring):
            inside = not inside
    return inside


def shape_to_rings(shape_obj: shapefile.Shape) -> List[List[Tuple[float, float]]]:
    rings: List[List[Tuple[float, float]]] = []
    points = shape_obj.points
    parts = list(shape_obj.parts) + [len(points)]
    for i in range(len(parts) - 1):
        start = parts[i]
        end = parts[i + 1]
        ring = [(pt[0], pt[1]) for pt in points[start:end]]
        if ring and ring[0] != ring[-1]:
            ring.append(ring[0])
        rings.append(ring)
    return rings


def load_south_america_polygons(shp_path: Path) -> List[CountryPolygon]:
    reader = shapefile.Reader(str(shp_path))
    polygons: List[CountryPolygon] = []
    for sr in reader.iterShapeRecords():
        rec = sr.record.as_dict()
        continent = rec.get("CONTINENT")
        if continent != "South America":
            continue
        country_name = rec.get("ADMIN") or rec.get("NAME_EN") or rec.get("NAME") or "Unknown"
        iso_a2 = rec.get("ISO_A2") or ""
        polygons.append(
            CountryPolygon(
                country_name=country_name,
                iso_a2=iso_a2,
                bbox=tuple(sr.shape.bbox),
                rings=shape_to_rings(sr.shape),
            )
        )
    return polygons


def load_city_index(cities_csv: Path) -> Dict[str, Dict[Tuple[int, int], List[CityPoint]]]:
    index: Dict[str, Dict[Tuple[int, int], List[CityPoint]]] = {}
    if not cities_csv.exists():
        return index
    with cities_csv.open("r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            name = str(row.get("name", "")).strip()
            if not name:
                continue
            lat = parse_float(row.get("latitude", ""))
            lon = parse_float(row.get("longitude", ""))
            cc = str(row.get("country_code", "")).strip().upper()
            if lat is None or lon is None or not cc:
                continue
            ascii_name = str(row.get("asciiname", "")).strip() or normalize_ascii(name)
            grid_key = (math.floor(lat), math.floor(lon))
            if cc not in index:
                index[cc] = {}
            if grid_key not in index[cc]:
                index[cc][grid_key] = []
            index[cc][grid_key].append(
                CityPoint(name=name, ascii_name=ascii_name, lat=lat, lon=lon, country_code=cc)
            )
    return index


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def nearest_city(
    lat: float,
    lon: float,
    country_iso_a2: str,
    city_index: Dict[str, Dict[Tuple[int, int], List[CityPoint]]],
) -> Tuple[Optional[CityPoint], Optional[float]]:
    country_data = city_index.get((country_iso_a2 or "").upper())
    if not country_data:
        return None, None
        
    best_city: Optional[CityPoint] = None
    best_dist = float("inf")
    
    lat_g, lon_g = math.floor(lat), math.floor(lon)
    for dl in (-1, 0, 1):
        for dL in (-1, 0, 1):
            grid_key = (lat_g + dl, lon_g + dL)
            for city in country_data.get(grid_key, []):
                dist = haversine_km(lat, lon, city.lat, city.lon)
                if dist < best_dist:
                    best_dist = dist
                    best_city = city

    if not best_city:
        for grid_cities in country_data.values():
            for city in grid_cities:
                dist = haversine_km(lat, lon, city.lat, city.lon)
                if dist < best_dist:
                    best_dist = dist
                    best_city = city

    if best_city:
        return best_city, best_dist
    return None, None


def classify_country(lat: float, lon: float, polygons: List[CountryPolygon]) -> Optional[CountryPolygon]:
    for country in polygons:
        if point_in_country(lon, lat, country):
            return country
    return None


def build_target_folder(
    base: str,
    status: str,
    country_name: str,
    city_ascii: str = "",
    date_folder: str = "Unknown_Date",
) -> str:
    if status == "Success":
        if city_ascii:
            return str(Path(base) / "SouthAmerica" / normalize_ascii(country_name) / normalize_ascii(city_ascii))
        return str(Path(base) / "SouthAmerica" / normalize_ascii(country_name))
    if status == "Success_Country_Others":
        return str(Path(base) / "SouthAmerica" / normalize_ascii(country_name) / "others" / date_folder)
    if status == "No_GPS":
        return str(Path(base) / "No_GPS" / date_folder)
    if status == "Invalid_GPS":
        return str(Path(base) / "Invalid_GPS" / date_folder)
    return str(Path(base) / "Other_Regions")


def ensure_schema(row: Dict[str, str]) -> Dict[str, str]:
    out: Dict[str, str] = {k: row.get(k, "") for k in SCHEMA_COLUMNS}
    for key, value in row.items():
        if key not in out:
            out[key] = value
    return out


def read_rows(input_csv: Path) -> List[Dict[str, str]]:
    with input_csv.open("r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        return list(reader)


def write_csv(output_csv: Path, rows: List[Dict[str, str]]) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    all_columns: List[str] = []
    for name in SCHEMA_COLUMNS:
        all_columns.append(name)
    for row in rows:
        for key in row.keys():
            if key not in all_columns:
                all_columns.append(key)
    with output_csv.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=all_columns)
        writer.writeheader()
        writer.writerows(rows)


def ensure_sqlite_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS media_metadata ("
        + ", ".join([f'"{c}" TEXT' for c in SCHEMA_COLUMNS])
        + ")"
    )
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(media_metadata)")}
    for col in SCHEMA_COLUMNS:
        if col not in existing_cols:
            conn.execute(f'ALTER TABLE media_metadata ADD COLUMN "{col}" TEXT')
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_media_metadata_unique_key ON media_metadata(unique_key)")


def write_sqlite(db_path: Path, rows: List[Dict[str, str]]) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_sqlite_schema(conn)
        placeholders = ", ".join(["?"] * len(SCHEMA_COLUMNS))
        insert_sql = f"INSERT OR IGNORE INTO media_metadata ({', '.join(SCHEMA_COLUMNS)}) VALUES ({placeholders})"
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        for row in rows:
            key = (row.get("unique_key") or "").strip()
            if not key:
                continue
            if not row.get("db_created_at"):
                row["db_created_at"] = now
            row["db_updated_at"] = row.get("db_updated_at") or ""
            payload = [str(row.get(col, "")) for col in SCHEMA_COLUMNS]
            before = conn.total_changes
            conn.execute(insert_sql, payload)
            inserted = conn.total_changes > before
            if inserted:
                continue
            conn.execute(
                "UPDATE media_metadata SET db_updated_at = ? WHERE unique_key = ?",
                (now, key),
            )
            row["db_updated_at"] = now
        conn.commit()
    finally:
        conn.close()


def enrich_file_stats(row: Dict[str, str]) -> None:
    file_path_value = row.get("file_path", "") or row.get("source_path", "")
    if not file_path_value:
        return
    file_path = Path(file_path_value)
    if not file_path.exists() or not file_path.is_file():
        return
    if not row.get("file_name"):
        row["file_name"] = file_path.name
    if not row.get("file_size_bytes"):
        row["file_size_bytes"] = str(file_path.stat().st_size)
    if not row.get("orientation"):
        row["orientation"] = compute_orientation(row.get("image_width", ""), row.get("image_height", ""))
    if not row.get("unique_key"):
        dt = row.get("datetime_original", "") or ""
        size = row.get("file_size_bytes", "") or ""
        partial_hash = ""
        try:
            partial_hash = partial_hash_file(file_path)
        except OSError:
            partial_hash = ""
        if partial_hash:
            row["unique_key"] = build_unique_key(size, dt, partial_hash)


def mark_duplicates(rows: List[Dict[str, str]], db_path: Optional[Path]) -> None:
    if not db_path:
        return
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_sqlite_schema(conn)
        existing = {
            row[0]
            for row in conn.execute("SELECT unique_key FROM media_metadata WHERE unique_key IS NOT NULL AND unique_key <> ''")
        }
    finally:
        conn.close()

    seen_batch = set()
    for row in rows:
        key = (row.get("unique_key") or "").strip()
        if not key:
            row["is_duplicate"] = "unknown"
            row["duplicate_reason"] = "missing_unique_key"
            continue
        if key in seen_batch:
            row["is_duplicate"] = "yes"
            row["duplicate_reason"] = "duplicate_in_current_batch"
            continue
        if key in existing:
            row["is_duplicate"] = "yes"
            row["duplicate_reason"] = "already_in_db"
            seen_batch.add(key)
            continue
        row["is_duplicate"] = "no"
        row["duplicate_reason"] = ""
        seen_batch.add(key)


def classify_rows(
    rows: List[Dict[str, str]],
    polygons: List[CountryPolygon],
    city_index: Dict[str, Dict[Tuple[int, int], List[CityPoint]]],
    lat_col: str,
    lon_col: str,
    target_root: str,
    max_city_distance_km: float,
    fallback_city: str,
) -> List[Dict[str, str]]:
    """Classify rows by country/city. Uses geo caching for performance."""
    output: List[Dict[str, str]] = []
    
    # Geographic caching: round lat/lon to 0.01 degree (~1km grid)
    # Most photos cluster near same location, so cache hit rate is high
    geo_cache: Dict[Tuple[float, float], Tuple[Optional[str], Optional[str]]] = {}
    
    for raw in rows:
        row = ensure_schema(raw)
        enrich_file_stats(row)
        date_folder = parse_date_folder(row.get("datetime_original", "") or raw.get("datetime_original", ""))

        lat = parse_float(raw.get(lat_col, row.get("gps_lat", "")))
        lon = parse_float(raw.get(lon_col, row.get("gps_lon", "")))

        if lat is None or lon is None:
            row["sort_status"] = "No_GPS"
            row["target_folder"] = build_target_folder(target_root, "No_GPS", "", date_folder=date_folder)
        elif lat < -90 or lat > 90 or lon < -180 or lon > 180:
            row["sort_status"] = "Invalid_GPS"
            row["target_folder"] = build_target_folder(target_root, "Invalid_GPS", "", date_folder=date_folder)
        else:
            row["gps_lat"] = f"{lat:.8f}"
            row["gps_lon"] = f"{lon:.8f}"
            
            # Geographic cache key (0.01 degree ~= 1km grid)
            # Photos often cluster in same location, so cache is effective
            cache_key = (round(lat, 2), round(lon, 2))
            
            if cache_key not in geo_cache:
                geo_cache[cache_key] = classify_country(lat, lon, polygons)
            
            country = geo_cache[cache_key]
            if country:
                row["geo_country"] = country.country_name
                city, city_dist_km = nearest_city(lat, lon, country.iso_a2, city_index)
                if city_dist_km is not None:
                    row["geo_city_distance_km"] = f"{city_dist_km:.3f}"
                if city and city_dist_km is not None and city_dist_km <= max_city_distance_km:
                    row["geo_city"] = city.name
                    row["geo_city_ascii"] = city.ascii_name or normalize_ascii(city.name)
                    row["sort_status"] = "Success"
                    row["target_folder"] = build_target_folder(
                        target_root,
                        "Success",
                        country.country_name,
                        row.get("geo_city_ascii", ""),
                        date_folder=date_folder,
                    )
                else:
                    row["geo_city"] = fallback_city
                    row["geo_city_ascii"] = normalize_ascii(fallback_city)
                    row["sort_status"] = "Success_Country_Others"
                    row["target_folder"] = build_target_folder(
                        target_root,
                        "Success_Country_Others",
                        country.country_name,
                        row.get("geo_city_ascii", ""),
                        date_folder=date_folder,
                    )
            else:
                row["sort_status"] = "Other_Regions"
                row["target_folder"] = build_target_folder(target_root, "Other_Regions", "")
        output.append(row)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="South America country classification MVP using Natural Earth polygons."
    )
    parser.add_argument("--input-csv", required=True, help="Input metadata CSV path")
    parser.add_argument(
        "--shapefile",
        default="Natural Earth_10m_admin_0_countries/ne_10m_admin_0_countries.shp",
        help="Natural Earth admin-0 countries .shp path",
    )
    parser.add_argument("--output-csv", default="metadata_country_result.csv", help="Output CSV path")
    parser.add_argument("--output-db", default="", help="Optional SQLite DB path")
    parser.add_argument("--lat-col", default="gps_lat", help="Input latitude column name")
    parser.add_argument("--lon-col", default="gps_lon", help="Input longitude column name")
    parser.add_argument("--cities-csv", default="my_cities.csv", help="City lookup CSV path")
    parser.add_argument("--target-root", default="output", help="Target root path stored in target_folder")
    parser.add_argument(
        "--max-city-distance-km",
        type=float,
        default=30.0,
        help="City assignment cutoff distance in km (default: 30.0)",
    )
    parser.add_argument(
        "--fallback-city",
        default="Unknown_City",
        help="Fallback city label when nearest city is farther than cutoff",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_csv = Path(args.input_csv)
    shp_path = Path(args.shapefile)
    output_csv = Path(args.output_csv)
    cities_csv = Path(args.cities_csv)

    if not input_csv.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_csv}")
    if not shp_path.exists():
        raise FileNotFoundError(f"Shapefile not found: {shp_path}")

    polygons = load_south_america_polygons(shp_path)
    if not polygons:
        raise RuntimeError("No South America polygons found in shapefile.")
    city_index = load_city_index(cities_csv)

    target_root = str((Path.cwd() / args.target_root).resolve()) if not Path(args.target_root).is_absolute() else args.target_root

    rows = read_rows(input_csv)
    enriched = classify_rows(
        rows=rows,
        polygons=polygons,
        city_index=city_index,
        lat_col=args.lat_col,
        lon_col=args.lon_col,
        target_root=target_root,
        max_city_distance_km=args.max_city_distance_km,
        fallback_city=args.fallback_city,
    )
    mark_duplicates(enriched, Path(args.output_db) if args.output_db else None)

    write_csv(output_csv, enriched)
    if args.output_db:
        write_sqlite(Path(args.output_db), enriched)

    print(f"Done: {len(enriched)} rows -> {output_csv}")
    if args.output_db:
        print(f"SQLite: {args.output_db}")


if __name__ == "__main__":
    main()
