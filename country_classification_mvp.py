import argparse
import csv
import hashlib
import math
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import shapefile


SCHEMA_COLUMNS = [
    "file_name",
    "file_type",
    "file_size_bytes",
    "file_hash",
    "datetime_original",
    "device_make",
    "device_model",
    "image_width",
    "image_height",
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


def hash_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as fp:
        while True:
            chunk = fp.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


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


def load_city_index(cities_csv: Path) -> Dict[str, List[CityPoint]]:
    index: Dict[str, List[CityPoint]] = {}
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
            index.setdefault(cc, []).append(
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
    city_index: Dict[str, List[CityPoint]],
) -> Tuple[Optional[CityPoint], Optional[float]]:
    cities = city_index.get((country_iso_a2 or "").upper(), [])
    if not cities:
        return None, None
    best_city: Optional[CityPoint] = None
    best_dist = float("inf")
    for city in cities:
        dist = haversine_km(lat, lon, city.lat, city.lon)
        if dist < best_dist:
            best_dist = dist
            best_city = city
    return best_city, best_dist


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


def write_sqlite(db_path: Path, rows: List[Dict[str, str]]) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("DROP TABLE IF EXISTS media_metadata")
        cols = ", ".join([f'"{c}" TEXT' for c in SCHEMA_COLUMNS])
        conn.execute(f"CREATE TABLE media_metadata ({cols})")
        placeholders = ", ".join(["?"] * len(SCHEMA_COLUMNS))
        insert_sql = f"INSERT INTO media_metadata ({', '.join(SCHEMA_COLUMNS)}) VALUES ({placeholders})"
        payload = [[str(row.get(col, "")) for col in SCHEMA_COLUMNS] for row in rows]
        conn.executemany(insert_sql, payload)
        conn.commit()
    finally:
        conn.close()


def enrich_file_stats(row: Dict[str, str], compute_hash: bool) -> None:
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
    if compute_hash and not row.get("file_hash"):
        row["file_hash"] = hash_file(file_path)


def classify_rows(
    rows: List[Dict[str, str]],
    polygons: List[CountryPolygon],
    city_index: Dict[str, List[CityPoint]],
    lat_col: str,
    lon_col: str,
    target_root: str,
    compute_hash: bool,
    max_city_distance_km: float,
    fallback_city: str,
) -> List[Dict[str, str]]:
    output: List[Dict[str, str]] = []
    for raw in rows:
        row = ensure_schema(raw)
        enrich_file_stats(row, compute_hash=compute_hash)
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
            country = classify_country(lat, lon, polygons)
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
    parser.add_argument(
        "--compute-hash",
        action="store_true",
        help="Compute SHA1 file hash when file_path/source_path exists (slower)",
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
        compute_hash=args.compute_hash,
        max_city_distance_km=args.max_city_distance_km,
        fallback_city=args.fallback_city,
    )

    write_csv(output_csv, enriched)
    if args.output_db:
        write_sqlite(Path(args.output_db), enriched)

    print(f"Done: {len(enriched)} rows -> {output_csv}")
    if args.output_db:
        print(f"SQLite: {args.output_db}")


if __name__ == "__main__":
    main()
