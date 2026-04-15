"""
Standalone VLM image tagger — Qwen3-VL-8B-Instruct Q4_K_M (GGUF)
Agentic RAG pipeline powered by LangGraph.

Pipeline per image:
  pre_filter ──(blurry/fail)──→ index
             └──(sharp)──→ infer → quality_check ──(fail)──→ infer (retry)
                                                  └─(pass)─→ geocode → enrich → embed → index → END

Dependencies: llama-cpp-python, pillow, voyageai, chromadb, langgraph

Usage:
    py -3.11 test_tagger.py <input_folder> [--output <folder>]
                            [--gpu-layers -1]
                            [--locationiq-key <KEY>]
                            [--voyage-key <KEY>] [--voyage-model voyage-multimodal-3]
                            [--chromadb <path>]

Output:
    output/<stem>.json   — per-image RAG-ready result
    output/summary.csv   — consolidated table
    <chromadb>/          — ChromaDB persistent store (if --chromadb set)
"""
# -*- coding: utf-8 -*-
import argparse
import base64
import csv
import hashlib
import io
import json
import os
import queue
import sys
import threading
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── .env loader (pure stdlib, no python-dotenv required) ─────────────────────

def _load_dotenv(env_path: Path) -> None:
    """Read key=value pairs from env_path and inject into os.environ (no-op if missing)."""
    if not env_path.exists():
        return
    with env_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, val)


# ── Paths ─────────────────────────────────────────────────────────────────────

_HERE       = Path(__file__).parent
GGUF_PATH   = _HERE / "models" / "Qwen3-VL-8B" / "Qwen3VL-8B-Instruct-Q4_K_M.gguf"
MMPROJ_PATH = _HERE / "models" / "Qwen3-VL-8B" / "mmproj-Qwen3VL-8B-Instruct-f16.gguf"
OUTPUT_DIR  = _HERE / "output"

# ── Constants ──────────────────────────────────────────────────────────────────

SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
N_GPU_LAYERS  = -1       # -1 = offload all layers to GPU; reduce (e.g. 24) on OOM
N_CTX         = 4096     # 1024 img tokens + prompt + response
MAX_TOKENS    = 384      # longer captions need more budget than 256
MAX_LONG_SIDE = 1024
MIN_LONG_SIDE = 512
VOYAGE_MODEL  = "voyage-multimodal-3"  # update to voyage-multimodal-3.5 when available
SHARPNESS_THRESHOLD = 8.0              # RMS of FIND_EDGES on 256×256 thumb; tune up to reject more blurry images
TRANSPORT_SCENES  = frozenset({"flight_cabin", "airport", "ground_transport"})

# ── VLM output schema ──────────────────────────────────────────────────────────

TAG_SCHEMA = {
    "type": "object",
    "properties": {
        "scene": {
            "type": "string",
            "enum": [
                # Outdoor / nature
                "street", "landscape", "beach", "wildlife",
                # Cultural / built environment
                "cultural_site", "market", "restaurant_cafe",
                # Accommodation
                "accommodation",
                # Portrait
                "portrait",
                # Transport — split into three distinct scenes
                "flight_cabin", "airport", "ground_transport",
                # Fallback
                "other",
            ],
        },
        "time_of_day": {
            "type": "string",
            "enum": ["dawn", "morning", "midday", "afternoon", "golden_hour", "dusk", "night"],
        },
        "activity": {
            "type": "string",
            "enum": [
                "sightseeing", "dining", "shopping", "hiking",
                "relaxing", "in_transit", "cultural", "wildlife_watching", "none",
            ],
        },
        "weather_condition": {
            "type": "string",
            "enum": ["sunny", "cloudy", "rainy", "snowy", "foggy", "indoor_or_na"],
        },
        "mood": {
            "type": "string",
            "enum": ["dramatic", "serene", "vibrant", "romantic", "adventurous", "melancholic", "playful", "neutral"],
        },
        "aesthetic_score":        {"type": "integer", "minimum": 1, "maximum": 10},
        "has_identifiable_faces": {"type": "boolean"},
        "objects":    {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        "attributes": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        "caption":    {"type": "string"},
    },
    "required": [
        "scene", "time_of_day", "activity", "weather_condition",
        "mood", "aesthetic_score", "has_identifiable_faces",
        "objects", "attributes", "caption",
    ],
    "additionalProperties": False,
}

# ── Prompts ────────────────────────────────────────────────────────────────────

PROMPT = (
    "Analyze this travel photo and return ONLY a JSON object (no markdown, no extra text).\n\n"
    "scene — pick the single most specific value:\n"
    "  street=city streets/alleys/plazas, landscape=nature/mountains/deserts/countryside,\n"
    "  beach=coast/sea/lake shore, wildlife=animals/nature close-up,\n"
    "  cultural_site=ruins/temples/monuments/museums/historic buildings,\n"
    "  market=markets/bazaars/souvenir stalls, restaurant_cafe=restaurants/cafes/bars/street food,\n"
    "  accommodation=hotel/hostel/Airbnb interior or exterior,\n"
    "  portrait=people as the dominant subject,\n"
    "  flight_cabin=inside an aircraft, airport=terminal/gate/runway/check-in area,\n"
    "  ground_transport=bus/train/taxi/car interior or exterior at a stop,\n"
    "  other=truly unclassifiable\n\n"
    "activity — primary purpose visible:\n"
    "  sightseeing=visiting attractions, dining=eating/drinking,\n"
    "  shopping=browsing goods, hiking=trekking/trails,\n"
    "  relaxing=resting/leisure, in_transit=traveling between places,\n"
    "  cultural=ceremonies/shows/events, wildlife_watching=observing animals, none=no clear activity\n\n"
    "time_of_day — infer from lighting, shadows, and sky color\n"
    "weather_condition — infer from sky and precipitation; use 'indoor_or_na' if indoors or sky not visible\n"
    "mood — overall emotional tone of the photo:\n"
    "  dramatic=strong contrast/tension/moody sky, serene=calm/peaceful/minimal,\n"
    "  vibrant=colorful/energetic/lively, romantic=warm/intimate/golden,\n"
    "  adventurous=exciting/vast/exploration, melancholic=somber/nostalgic/overcast,\n"
    "  playful=fun/lighthearted/bright, neutral=no strong mood\n"
    "aesthetic_score — integer 1-10; reserve 7-10 for sharp, well-composed, magazine-worthy shots:\n"
    "  1-4: blurry, poorly lit, cluttered, unflattering angle\n"
    "  5-6: acceptable snapshot, average composition\n"
    "  7-10: ONLY for well-composed, sharp, visually striking photos worthy of a luxury travel magazine\n"
    "has_identifiable_faces — true only if one or more faces are clearly recognizable\n"
    "objects — up to 8 specific subjects or objects (be specific: 'stone archway' not 'arch')\n"
    "attributes — up to 3 visual qualities (lighting type, mood, dominant color/texture)\n"
    "caption — 2-4 sentences in English: scene type, key objects, atmosphere, cultural context.\n"
    "  Include location only if visible in image or confirmed by the metadata block below.\n"
)

RETRY_PROMPT = (
    "The previous analysis was too generic. Look more carefully and be more specific.\n"
    "Return ONLY a JSON object (no markdown, no extra text).\n\n"
    "scene — avoid 'other'; choose the most precise match:\n"
    "  street, landscape, beach, wildlife, cultural_site, market, restaurant_cafe,\n"
    "  accommodation, portrait, flight_cabin, airport, ground_transport, other\n\n"
    "activity — must match the scene logically (e.g. airport → in_transit, not sightseeing):\n"
    "  sightseeing, dining, shopping, hiking, relaxing, in_transit, cultural, wildlife_watching, none\n\n"
    "time_of_day — infer carefully from shadows, haze, color temperature, and sky\n"
    "weather_condition — infer from sky, precipitation, and overall lighting\n"
    "mood — emotional tone (dramatic/serene/vibrant/romantic/adventurous/melancholic/playful/neutral)\n"
    "aesthetic_score — integer 1-10; reserve 7-10 for sharp, well-composed, magazine-worthy shots\n"
    "has_identifiable_faces — true only if faces are clearly recognizable\n"
    "objects — 4-8 SPECIFIC items visible (e.g. 'leather saddle' not 'object')\n"
    "attributes — 3 specific visual qualities (e.g. 'golden hour backlight', 'turquoise glacial water')\n"
    "caption — 2-4 sentences: scene type, specific objects, atmosphere, cultural context.\n"
    "  Include location only if visible or confirmed by the metadata block below.\n"
)

_SENTINEL = object()

# ── Dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class GeoInfo:
    place: str = ""
    neighbourhood: str = ""
    city: str = ""
    state: str = ""
    country: str = ""
    country_code: str = ""


@dataclass
class TagResult:
    path: Path
    photo_id: str = ""
    file_path: str = ""
    capture_datetime: str = ""
    scene: str = "other"
    time_of_day: str = ""
    activity: str = ""
    weather_condition: str = ""
    mood: str = ""
    aesthetic_score: int = 0
    has_identifiable_faces: bool = False
    objects: List[str] = field(default_factory=list)
    attributes: List[str] = field(default_factory=list)
    caption: str = ""
    gps_lat: str = ""
    gps_lon: str = ""
    geo: GeoInfo = field(default_factory=GeoInfo)
    context: str = ""
    season: str = ""             # spring/summer/autumn/winter — computed from EXIF date + GPS latitude
    location_confidence: str = ""  # "high" / "medium" (transport) / "low" (no GPS)
    retrieval_text: str = ""
    multimodal_embedding: List[float] = field(default_factory=list)
    retry_count: int = 0
    error: str = ""


# ── GPS from EXIF ──────────────────────────────────────────────────────────────

def _dms_to_dd(dms, ref: str) -> Optional[float]:
    try:
        d, m, s = float(dms[0]), float(dms[1]), float(dms[2])
        dd = d + m / 60.0 + s / 3600.0
        return -dd if ref in ("S", "W") else dd
    except Exception:
        return None


def _get_gps(img_path: Path) -> Tuple[str, str]:
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS, GPSTAGS
        with Image.open(img_path) as img:
            raw = img._getexif()  # type: ignore[attr-defined]
        if not raw:
            return "", ""
        gps_tag = next((k for k, v in TAGS.items() if v == "GPSInfo"), None)
        if gps_tag is None or gps_tag not in raw:
            return "", ""
        gps = {GPSTAGS.get(k, k): v for k, v in raw[gps_tag].items()}
        lat = _dms_to_dd(gps.get("GPSLatitude", ()), gps.get("GPSLatitudeRef", ""))
        lon = _dms_to_dd(gps.get("GPSLongitude", ()), gps.get("GPSLongitudeRef", ""))
        return (f"{lat:.6f}" if lat is not None else ""), (f"{lon:.6f}" if lon is not None else "")
    except Exception:
        return "", ""


# ── Datetime from EXIF ─────────────────────────────────────────────────────────

def _get_datetime(img_path: Path) -> str:
    """Extract capture datetime from EXIF. Returns ISO 8601 string or empty."""
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
        with Image.open(img_path) as img:
            raw = img._getexif()  # type: ignore[attr-defined]
        if not raw:
            return ""
        tag_map = {v: k for k, v in TAGS.items()}
        for tag_name in ("DateTimeOriginal", "DateTime"):
            tag_id = tag_map.get(tag_name)
            if tag_id and tag_id in raw:
                dt_str = raw[tag_id]  # "2026:01:15 14:32:00"
                if len(dt_str) >= 19:
                    return dt_str[:10].replace(":", "-") + "T" + dt_str[11:19]
    except Exception:
        pass
    return ""


# ── LocationIQ reverse geocoding ───────────────────────────────────────────────

_geo_cache: Dict[Tuple[str, str], GeoInfo] = {}
_GEO_CACHE_PATH = _HERE / "geo_cache.json"


def _load_geo_cache() -> None:
    """Load persisted geo cache from disk into _geo_cache."""
    if not _GEO_CACHE_PATH.exists():
        return
    try:
        data = json.loads(_GEO_CACHE_PATH.read_text(encoding="utf-8"))
        for key_str, v in data.items():
            lat, _, lon = key_str.partition("|")
            _geo_cache[(lat, lon)] = GeoInfo(
                place=v.get("place", ""),
                neighbourhood=v.get("neighbourhood", ""),
                city=v.get("city", ""),
                state=v.get("state", ""),
                country=v.get("country", ""),
                country_code=v.get("country_code", ""),
            )
    except Exception as e:
        print(f"[geo_cache] load error: {e}", file=sys.stderr)


def _save_geo_cache_entry(lat: str, lon: str, geo: GeoInfo) -> None:
    """Persist a single geo result to disk cache."""
    try:
        data: Dict[str, Any] = {}
        if _GEO_CACHE_PATH.exists():
            data = json.loads(_GEO_CACHE_PATH.read_text(encoding="utf-8"))
        data[f"{lat}|{lon}"] = {
            "place": geo.place, "neighbourhood": geo.neighbourhood,
            "city": geo.city, "state": geo.state,
            "country": geo.country, "country_code": geo.country_code,
        }
        _GEO_CACHE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[geo_cache] save error: {e}", file=sys.stderr)


def reverse_geocode(lat: str, lon: str, api_key: str) -> GeoInfo:
    """Call LocationIQ reverse geocode API. Results are cached per (lat, lon)."""
    key = (lat, lon)
    if key in _geo_cache:
        return _geo_cache[key]
    if not lat or not lon or not api_key:
        return GeoInfo()
    url = (
        f"https://us1.locationiq.com/v1/reverse"
        f"?key={urllib.parse.quote(api_key)}"
        f"&lat={urllib.parse.quote(lat)}"
        f"&lon={urllib.parse.quote(lon)}"
        f"&format=xml&zoom=18"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "photo-tagger/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            xml_bytes = resp.read()
        root = ET.fromstring(xml_bytes)
        addr = root.find("addressparts")
        if addr is None:
            return GeoInfo()

        def _get(*tags: str) -> str:
            for tag in tags:
                el = addr.find(tag)
                if el is not None and el.text:
                    return el.text.strip()
            return ""

        geo = GeoInfo(
            place=_get("isolated_dwelling", "amenity", "tourism", "shop", "building"),
            neighbourhood=_get("neighbourhood", "suburb", "quarter"),
            city=_get("city", "town", "village", "municipality"),
            state=_get("state"),
            country=_get("country"),
            country_code=_get("country_code"),
        )
        _geo_cache[key] = geo
        _save_geo_cache_entry(lat, lon, geo)   # persist to disk
        return geo
    except Exception as e:
        print(f"  [geocode error] {lat},{lon}: {e}", file=sys.stderr)
        return GeoInfo()


# ── Folder context ─────────────────────────────────────────────────────────────

_SKIP = {"output", "input", "photos", "images", "raw"}


def _folder_context(img_path: Path) -> str:
    keep = [
        p for p in img_path.parts[-6:-1]
        if p.lower() not in _SKIP
        and not p.replace(".", "").replace("-", "").replace("_", "").isdigit()
        and len(p) > 2
    ]
    return ", ".join(keep[-3:])


# ── Photo ID ───────────────────────────────────────────────────────────────────

def _compute_photo_id(img_path: Path) -> str:
    """Stable 16-char ID derived from first 64KB of file bytes."""
    try:
        with img_path.open("rb") as f:
            chunk = f.read(65536)
        return hashlib.sha1(chunk).hexdigest()[:16]
    except Exception:
        return hashlib.sha1(img_path.name.encode()).hexdigest()[:16]


# ── Voyage multimodal embedding ────────────────────────────────────────────────

def _embed_voyage(b64: str, retrieval_text: str, client: Any, model: str) -> List[float]:
    """Embed image + retrieval_text together using Voyage multimodal API."""
    if not client or not b64:
        return []
    try:
        from PIL import Image
        pil_img = Image.open(io.BytesIO(base64.b64decode(b64)))
        result = client.multimodal_embed(
            inputs=[[pil_img, retrieval_text]],
            model=model,
            input_type="document",
        )
        return result.embeddings[0]
    except Exception as e:
        print(f"  [voyage error] {e}", file=sys.stderr)
        return []


# ── ChromaDB ───────────────────────────────────────────────────────────────────

def _get_chroma_collection(db_path: str, collection_name: str = "travel_photos") -> Any:
    import chromadb
    client = chromadb.PersistentClient(path=db_path)
    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def _chroma_upsert(collection: Any, r: "TagResult") -> bool:
    """Upsert to ChromaDB. Returns False if skipped.

    - voyage embedding available  → custom multimodal vectors (travel_photos)
    - no voyage embedding         → ChromaDB auto-embeds retrieval_text (travel_photos_text)
    Both paths skip aesthetic < 6 or face-flagged photos.
    """
    if r.error or not r.photo_id or not r.retrieval_text:
        return False
    # Blog-ready filter: require aesthetic quality ≥ 6 and no identifiable faces
    if r.aesthetic_score < 6 or r.has_identifiable_faces:
        return False
    metadata = {
        "file":                   r.path.name,
        "file_path":              r.file_path,
        "scene":                  r.scene,
        "time_of_day":            r.time_of_day,
        "activity":               r.activity,
        "weather_condition":      r.weather_condition,
        "mood":                   r.mood,
        "aesthetic_score":        r.aesthetic_score,
        "has_identifiable_faces": r.has_identifiable_faces,
        "geo_city":               r.geo.city,
        "geo_state":              r.geo.state,
        "geo_country":            r.geo.country,
        "geo_country_code":       r.geo.country_code,
        "gps_lat":                r.gps_lat,
        "gps_lon":                r.gps_lon,
        "capture_datetime":       r.capture_datetime,
        "season":                 r.season,
        "location_confidence":    r.location_confidence,
    }
    try:
        if r.multimodal_embedding:
            # Voyage multimodal path: pass custom embeddings directly
            collection.upsert(
                ids=[r.photo_id],
                embeddings=[r.multimodal_embedding],
                documents=[r.retrieval_text],
                metadatas=[metadata],
            )
        else:
            # Text-only path: ChromaDB auto-embeds retrieval_text via default model
            collection.upsert(
                ids=[r.photo_id],
                documents=[r.retrieval_text],
                metadatas=[metadata],
            )
        return True
    except Exception as e:
        print(f"  [chroma error] {e}", file=sys.stderr)
        return False


# ── Image preprocessing (CPU, producer thread) ────────────────────────────────

def _preprocess(img_path: Path) -> Optional[str]:
    """Resize and encode image to base64 JPEG. Returns None on failure."""
    try:
        from PIL import Image
        with Image.open(img_path) as img:
            w, h = img.size
            long_side = max(w, h)
            if long_side < MIN_LONG_SIDE:
                scale = MIN_LONG_SIDE / long_side
                img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            elif long_side > MAX_LONG_SIDE:
                img.thumbnail((MAX_LONG_SIDE, MAX_LONG_SIDE), Image.LANCZOS)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
        return base64.standard_b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"  [preprocess error] {img_path.name}: {e}", file=sys.stderr)
        return None


def _compute_sharpness(b64: str) -> float:
    """Estimate image sharpness via RMS of FIND_EDGES on a 256×256 grayscale thumbnail.
    Lower = blurrier. Typical range: blurry ≈ 3-7, normal ≈ 10-25.
    Adjust SHARPNESS_THRESHOLD to taste.
    """
    try:
        from PIL import Image, ImageFilter
        pil_img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("L")
        thumb = pil_img.resize((256, 256), Image.LANCZOS)
        edges = thumb.filter(ImageFilter.FIND_EDGES)
        pixels = list(edges.getdata())
        rms = (sum(p * p for p in pixels) / len(pixels)) ** 0.5
        return rms
    except Exception:
        return 999.0  # if computation fails, don't block the image


def _producer(files: List[Path], q: "queue.Queue") -> None:
    for path in files:
        b64 = _preprocess(path)
        gps = _get_gps(path)
        dt  = _get_datetime(path)
        ctx = _folder_context(path)
        q.put((path, b64, gps, dt, ctx))
    q.put(_SENTINEL)


# ── LLM call ──────────────────────────────────────────────────────────────────

def _call_llm(llm: Any, grammar: Any, b64: str, user_text: str) -> dict:
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": user_text},
            ],
        }
    ]
    resp = llm.create_chat_completion(
        messages=messages,
        grammar=grammar,
        max_tokens=MAX_TOKENS,
        temperature=0.1,
    )
    raw = resp["choices"][0]["message"]["content"]
    return json.loads(raw)


# ── LangGraph: State & Nodes ───────────────────────────────────────────────────

try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict  # type: ignore[assignment]


class ImageState(TypedDict):
    path:                 Path
    b64:                  Optional[str]
    gps_lat:              str
    gps_lon:              str
    capture_datetime:     str
    context:              str
    # VLM output
    scene:                  str
    time_of_day:            str
    activity:               str
    weather_condition:      str
    mood:                   str
    aesthetic_score:        int
    has_identifiable_faces: bool
    objects:                List[str]
    attributes:             List[str]
    caption:                str
    # Control
    retry_count:            int
    # Enrichment
    geo:                    GeoInfo
    photo_id:               str
    file_path:              str
    season:                 str
    location_confidence:    str
    retrieval_text:         str
    multimodal_embedding:   List[float]
    error:                  str


def _node_prefilter(state: ImageState, *, output_dir: Path, force: bool) -> ImageState:
    """Compute photo_id + file_path, skip duplicates and blurry images."""
    path      = state["path"]
    photo_id  = _compute_photo_id(path)
    file_path = str(path.resolve())
    b64       = state.get("b64")

    if not b64:
        return {**state, "photo_id": photo_id, "file_path": file_path,
                "error": "preprocess_failed"}

    # Skip already-processed images unless --force
    if not force:
        out_json = output_dir / (path.stem + ".json")
        if out_json.exists():
            try:
                existing = json.loads(out_json.read_text(encoding="utf-8"))
                if existing.get("photo_id") == photo_id and not existing.get("error"):
                    return {**state, "photo_id": photo_id, "file_path": file_path,
                            "error": "already_processed"}
            except Exception:
                pass  # corrupted JSON → re-process

    sharpness = _compute_sharpness(b64)
    if sharpness < SHARPNESS_THRESHOLD:
        return {
            **state, "photo_id": photo_id, "file_path": file_path,
            "error": f"blurry_image (sharpness={sharpness:.1f}<{SHARPNESS_THRESHOLD})",
        }
    return {**state, "photo_id": photo_id, "file_path": file_path}


def _route_prefilter(state: ImageState) -> str:
    """Route to 'infer' if sharp, 'skip' (→ index) if blurry or preprocess failed."""
    return "skip" if state.get("error") else "infer"


def _node_infer(state: ImageState, *, llm: Any, grammar: Any) -> ImageState:
    """VLM inference node. Uses RETRY_PROMPT on second attempt."""
    prompt = RETRY_PROMPT if state["retry_count"] > 0 else PROMPT

    # Build metadata hint block so VLM can cross-validate time_of_day, location, etc.
    meta_lines = []
    cap_dt = state.get("capture_datetime", "")
    if cap_dt:
        try:
            dt_obj = datetime.fromisoformat(cap_dt)
            human_time = dt_obj.strftime("%-I:%M %p, %B %-d %Y")  # "12:38 PM, March 31 2026"
        except Exception:
            try:
                # Windows strftime doesn't support %-I; fall back
                dt_obj = datetime.fromisoformat(cap_dt)
                human_time = dt_obj.strftime("%I:%M %p, %B %d %Y").lstrip("0")
            except Exception:
                human_time = cap_dt
        meta_lines.append(f"- Capture time: {human_time}")
    if state.get("gps_lat") and state.get("gps_lon"):
        meta_lines.append(f"- GPS: {state['gps_lat']}, {state['gps_lon']}")
    if state.get("context"):
        meta_lines.append(f"- Folder context: {state['context']}")

    if meta_lines:
        meta_block = (
            "[Photo Metadata — use to cross-validate your analysis, especially time_of_day]\n"
            + "\n".join(meta_lines)
        )
        user_text = f"{prompt}\n\n{meta_block}"
    else:
        user_text = prompt

    try:
        data = _call_llm(llm, grammar, state["b64"], user_text)
        return {
            **state,
            "scene":                  data.get("scene", "other"),
            "time_of_day":            data.get("time_of_day", ""),
            "activity":               data.get("activity", ""),
            "weather_condition":      data.get("weather_condition", ""),
            "mood":                   data.get("mood", "neutral"),
            "aesthetic_score":        int(data.get("aesthetic_score", 0)),
            "has_identifiable_faces": bool(data.get("has_identifiable_faces", False)),
            "objects":                data.get("objects", [])[:8],
            "attributes":             data.get("attributes", [])[:3],
            "caption":                data.get("caption", ""),
            "retry_count":            state["retry_count"] + 1,
        }
    except Exception as e:
        return {**state, "error": str(e)[:120], "retry_count": state["retry_count"] + 1}


def _node_quality_check(state: ImageState) -> ImageState:
    """Pass-through node; routing is handled by _route_quality."""
    return state


def _is_low_quality(state: ImageState) -> bool:
    return (
        state.get("scene") == "other"
        or len(state.get("objects", [])) < 3
        or len(state.get("caption", "")) < 50
    )


def _route_quality(state: ImageState) -> str:
    """Return 'retry' only after the first inference attempt and if quality is poor."""
    if _is_low_quality(state) and state["retry_count"] == 1 and not state.get("error"):
        return "retry"
    return "proceed"


def _node_geocode(state: ImageState, *, api_key: str) -> ImageState:
    if state.get("error") or not state["gps_lat"] or not state["gps_lon"]:
        return state
    geo = reverse_geocode(state["gps_lat"], state["gps_lon"], api_key)
    return {**state, "geo": geo}


def _compute_season(capture_datetime: str, gps_lat: str) -> str:
    """Compute meteorological season from EXIF date + GPS latitude (hemisphere-aware)."""
    if not capture_datetime:
        return ""
    try:
        month = datetime.fromisoformat(capture_datetime).month
        # Southern hemisphere (negative latitude): seasons are flipped
        is_southern = float(gps_lat) < 0 if gps_lat else False
        if month in (3, 4, 5):
            return "autumn" if is_southern else "spring"
        elif month in (6, 7, 8):
            return "winter" if is_southern else "summer"
        elif month in (9, 10, 11):
            return "spring" if is_southern else "autumn"
        else:  # 12, 1, 2
            return "summer" if is_southern else "winter"
    except Exception:
        return ""


def _node_enrich(state: ImageState) -> ImageState:
    """Compute season, location_confidence, and build natural-language retrieval_text."""
    geo: GeoInfo = state.get("geo") or GeoInfo()
    scene       = state.get("scene", "")
    time_of_day = state.get("time_of_day", "")
    activity    = state.get("activity", "")
    weather     = state.get("weather_condition", "")
    mood        = state.get("mood", "")
    caption     = (state.get("caption", "") or "").strip()
    objects     = state.get("objects", [])
    season      = _compute_season(state.get("capture_datetime", ""), state.get("gps_lat", ""))

    # Location confidence: transport GPS reflects en-route position, not destination
    in_transport = scene in TRANSPORT_SCENES
    has_gps      = bool(state.get("gps_lat") and state.get("gps_lon"))
    if not has_gps:
        location_confidence = "low"
    elif in_transport:
        location_confidence = "medium"
    else:
        location_confidence = "high"

    # Location string — suppress city for transport scenes with medium confidence
    if location_confidence == "medium":
        loc = ", ".join(filter(None, [geo.state, geo.country]))
    else:
        loc = ", ".join(filter(None, [geo.city, geo.state, geo.country]))

    # Build natural-language retrieval_text for semantic search
    sentences: List[str] = []
    if caption:
        sentences.append(caption.rstrip(".") + ".")
    scene_str    = scene.replace("_", " ")
    activity_str = activity.replace("_", " ")
    time_str     = time_of_day.replace("_", " ")
    sentences.append(
        f"This is a {scene_str} scene during {time_str}, featuring {activity_str} activity."
    )
    if objects:
        sentences.append(f"Notable elements: {', '.join(objects[:6])}.")
    if weather and weather not in ("indoor_or_na", ""):
        sentences.append(f"Weather: {weather.replace('_', ' ')}.")
    if mood and mood != "neutral":
        sentences.append(f"Mood: {mood}.")
    if season:
        sentences.append(f"Season: {season}.")
    if loc:
        if location_confidence == "low":
            sentences.append(
                f"Approximate location: {loc} (folder context only — no GPS)."
            )
        elif location_confidence == "medium":
            sentences.append(
                f"Approximate location: {loc} (GPS reflects transit route, not destination)."
            )
        else:
            sentences.append(f"Location: {loc}.")

    retrieval_text = " ".join(sentences)
    return {**state, "season": season, "location_confidence": location_confidence, "retrieval_text": retrieval_text}


def _node_embed(state: ImageState, *, voyage_client: Any, voyage_model: str) -> ImageState:
    if state.get("error") or not voyage_client or not state.get("b64"):
        return state
    emb = _embed_voyage(state["b64"], state.get("retrieval_text", ""), voyage_client, voyage_model)
    return {**state, "multimodal_embedding": emb}


def _node_index(state: ImageState, *, output_dir: Path, chroma_col: Any) -> ImageState:
    """Write JSON output and upsert to ChromaDB. Skips already-processed images."""
    if state.get("error") == "already_processed":
        return state  # existing JSON is valid — don't overwrite
    r = _state_to_tagresult(state)
    _write_json(output_dir, r)
    if chroma_col:
        _chroma_upsert(chroma_col, r)
    return state


def _state_to_tagresult(state: ImageState) -> TagResult:
    return TagResult(
        path=state["path"],
        photo_id=state.get("photo_id", ""),
        file_path=state.get("file_path", str(state["path"])),
        capture_datetime=state.get("capture_datetime", ""),
        scene=state.get("scene", "other"),
        time_of_day=state.get("time_of_day", ""),
        activity=state.get("activity", ""),
        weather_condition=state.get("weather_condition", ""),
        mood=state.get("mood", ""),
        aesthetic_score=int(state.get("aesthetic_score", 0)),
        has_identifiable_faces=bool(state.get("has_identifiable_faces", False)),
        objects=state.get("objects", []),
        attributes=state.get("attributes", []),
        caption=state.get("caption", ""),
        gps_lat=state.get("gps_lat", ""),
        gps_lon=state.get("gps_lon", ""),
        geo=state.get("geo") or GeoInfo(),
        context=state.get("context", ""),
        season=state.get("season", ""),
        location_confidence=state.get("location_confidence", ""),
        retrieval_text=state.get("retrieval_text", ""),
        multimodal_embedding=state.get("multimodal_embedding", []),
        retry_count=state.get("retry_count", 0),
        error=state.get("error", ""),
    )


def _build_graph(
    llm: Any,
    grammar: Any,
    locationiq_key: str,
    voyage_client: Any,
    voyage_model: str,
    chroma_col: Any,
    output_dir: Path,
    force: bool = False,
) -> Any:
    from langgraph.graph import StateGraph, END

    workflow: StateGraph = StateGraph(ImageState)
    workflow.add_node("pre_filter",    partial(_node_prefilter, output_dir=output_dir, force=force))
    workflow.add_node("infer",         partial(_node_infer, llm=llm, grammar=grammar))
    workflow.add_node("quality_check", _node_quality_check)
    workflow.add_node("geocode",       partial(_node_geocode, api_key=locationiq_key))
    workflow.add_node("enrich",        _node_enrich)
    workflow.add_node("embed",         partial(_node_embed, voyage_client=voyage_client, voyage_model=voyage_model))
    workflow.add_node("index",         partial(_node_index, output_dir=output_dir, chroma_col=chroma_col))

    workflow.set_entry_point("pre_filter")
    workflow.add_conditional_edges(
        "pre_filter", _route_prefilter,
        {"infer": "infer", "skip": "index"},
    )
    workflow.add_edge("infer", "quality_check")
    workflow.add_conditional_edges(
        "quality_check", _route_quality,
        {"retry": "infer", "proceed": "geocode"},
    )
    workflow.add_edge("geocode", "enrich")
    workflow.add_edge("enrich", "embed")
    workflow.add_edge("embed", "index")
    workflow.add_edge("index", END)

    return workflow.compile()


# ── Output writers ─────────────────────────────────────────────────────────────

def _write_json(output_dir: Path, r: TagResult) -> None:
    data = {
        "photo_id":           r.photo_id,
        "file":               r.path.name,
        "file_path":          r.file_path,
        "capture_datetime":   r.capture_datetime,
        "scene":              r.scene,
        "time_of_day":        r.time_of_day,
        "activity":           r.activity,
        "weather_condition":  r.weather_condition,
        "mood":               r.mood,
        "aesthetic_score":        r.aesthetic_score,
        "has_identifiable_faces": r.has_identifiable_faces,
        "objects":            r.objects,
        "attributes":         r.attributes,
        "caption":            r.caption,
        "gps_lat":            r.gps_lat,
        "gps_lon":            r.gps_lon,
        "geo_place":          r.geo.place,
        "geo_neighbourhood":  r.geo.neighbourhood,
        "geo_city":           r.geo.city,
        "geo_state":          r.geo.state,
        "geo_country":        r.geo.country,
        "geo_country_code":   r.geo.country_code,
        "context":            r.context,
        "season":             r.season,
        "location_confidence": r.location_confidence,
        "retrieval_text":     r.retrieval_text,
        "multimodal_embedding": r.multimodal_embedding,
        "error":              r.error,
    }
    out = output_dir / (r.path.stem + ".json")
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


_CSV_FIELDS = [
    "photo_id", "file_name", "file_path", "capture_datetime",
    "scene", "time_of_day", "activity", "weather_condition", "mood",
    "aesthetic_score", "has_identifiable_faces",
    "objects", "attributes", "caption",
    "gps_lat", "gps_lon",
    "geo_place", "geo_neighbourhood", "geo_city", "geo_state", "geo_country", "geo_country_code",
    "context", "season", "location_confidence", "retrieval_text", "error",
]


def _write_csv(results: List[TagResult], csv_path: Path) -> None:
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        w.writeheader()
        for r in results:
            w.writerow({
                "photo_id":          r.photo_id,
                "file_name":         r.path.name,
                "file_path":         r.file_path,
                "capture_datetime":  r.capture_datetime,
                "scene":             r.scene,
                "time_of_day":       r.time_of_day,
                "activity":          r.activity,
                "weather_condition": r.weather_condition,
                "mood":              r.mood,
                "aesthetic_score":        r.aesthetic_score,
                "has_identifiable_faces": r.has_identifiable_faces,
                "objects":           "|".join(r.objects),
                "attributes":        "|".join(r.attributes),
                "caption":           r.caption,
                "gps_lat":           r.gps_lat,
                "gps_lon":           r.gps_lon,
                "geo_place":         r.geo.place,
                "geo_neighbourhood": r.geo.neighbourhood,
                "geo_city":          r.geo.city,
                "geo_state":         r.geo.state,
                "geo_country":       r.geo.country,
                "geo_country_code":  r.geo.country_code,
                "context":           r.context,
                "season":            r.season,
                "location_confidence": r.location_confidence,
                "retrieval_text":    r.retrieval_text,
                "error":             r.error,
            })


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    _load_dotenv(_HERE / ".env")   # load .env before argparse reads env vars

    parser = argparse.ArgumentParser(description="Agentic VLM image tagger for travel RAG pipelines")
    parser.add_argument("input", help="Folder containing images to tag")
    parser.add_argument("--output", default=str(OUTPUT_DIR), help="Output folder (default: ./output)")
    parser.add_argument("--gpu-layers", type=int, default=N_GPU_LAYERS,
                        help=f"GPU layers to offload (default: {N_GPU_LAYERS}; try 24 on OOM)")
    parser.add_argument("--locationiq-key", default=os.environ.get("LOCATIONIQ_API_KEY", ""),
                        help="LocationIQ API key (or set LOCATIONIQ_API_KEY in .env)")
    parser.add_argument("--voyage-key", default=os.environ.get("VOYAGE_API_KEY", ""),
                        help="Voyage AI API key for multimodal embeddings (or set VOYAGE_API_KEY in .env)")
    parser.add_argument("--voyage-model", default=VOYAGE_MODEL,
                        help=f"Voyage embedding model (default: {VOYAGE_MODEL})")
    parser.add_argument("--chromadb", default=str(_HERE / "chroma_db"),
                        help="ChromaDB persist directory (default: ./chroma_db)")
    parser.add_argument("--force", action="store_true",
                        help="Re-process images that already have output JSON (skip dedup check)")
    args = parser.parse_args()

    input_dir  = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    _load_geo_cache()
    if _geo_cache:
        print(f"Geo cache loaded:      {len(_geo_cache)} entries from {_GEO_CACHE_PATH.name}", flush=True)

    print(f"LocationIQ geocoding:  {'enabled' if args.locationiq_key else 'disabled'}", flush=True)
    print(f"Voyage embedding:      {'enabled (' + args.voyage_model + ')' if args.voyage_key else 'disabled'}", flush=True)
    print(f"ChromaDB:              {args.chromadb if args.chromadb else 'disabled'}", flush=True)

    for label, p in [("Model", GGUF_PATH), ("mmproj", MMPROJ_PATH)]:
        if not p.exists():
            sys.exit(f"{label} not found: {p}")

    files = sorted(
        p for p in input_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXT
    )
    if not files:
        sys.exit(f"No supported images in {input_dir}")

    print(f"Found {len(files)} images. Loading model (gpu_layers={args.gpu_layers})...", flush=True)

    try:
        from llama_cpp import Llama, LlamaGrammar
    except ModuleNotFoundError:
        sys.exit(
            "[ERROR] llama_cpp not found.\n"
            "Install with:  py -3.11 -m pip install <JamePeng wheel>"
        )

    # Handler auto-detection: JamePeng fork uses Qwen3VLChatHandler / Qwen25VLChatHandler
    _VLHandler = None
    for _name in ("Qwen3VLChatHandler", "Qwen25VLChatHandler", "Qwen2VLChatHandler"):
        try:
            import importlib
            _mod = importlib.import_module("llama_cpp.llama_chat_format")
            _VLHandler = getattr(_mod, _name)
            print(f"Using {_name}", flush=True)
            break
        except (ImportError, AttributeError):
            continue
    if _VLHandler is None:
        sys.exit(
            "[ERROR] No Qwen VL chat handler found.\n"
            "Install JamePeng fork:\n"
            "  pip install 'https://github.com/JamePeng/llama-cpp-python/releases/...'"
        )

    # image_min_tokens=1024 fixes Qwen VL vision encoding warnings
    vl_kwargs: Dict[str, Any] = {"clip_model_path": str(MMPROJ_PATH), "verbose": False}
    try:
        import inspect
        if "image_min_tokens" in inspect.signature(_VLHandler.__init__).parameters:
            vl_kwargs["image_min_tokens"] = 1024
    except Exception:
        pass
    chat_handler = _VLHandler(**vl_kwargs)
    llm = Llama(
        model_path=str(GGUF_PATH),
        chat_handler=chat_handler,
        n_gpu_layers=args.gpu_layers,
        n_ctx=N_CTX,
        verbose=False,
    )
    grammar = LlamaGrammar.from_json_schema(json.dumps(TAG_SCHEMA))
    print("Model ready.", flush=True)

    # Optional: Voyage client
    voyage_client = None
    if args.voyage_key:
        try:
            import voyageai
            voyage_client = voyageai.Client(api_key=args.voyage_key)
        except ImportError:
            print("[warn] voyageai not installed — pip install voyageai", file=sys.stderr)

    # ChromaDB collection
    # Use 'travel_photos' (voyage multimodal) or 'travel_photos_text' (ChromaDB auto-embed)
    # Two separate collections prevent dimension conflicts when switching embedding modes.
    chroma_col = None
    if args.chromadb:
        try:
            collection_name = "travel_photos" if voyage_client else "travel_photos_text"
            chroma_col = _get_chroma_collection(args.chromadb, collection_name)
            print(f"ChromaDB '{collection_name}': {chroma_col.count()} existing docs  [{args.chromadb}]", flush=True)
        except ImportError:
            print("[warn] chromadb not installed — pip install chromadb", file=sys.stderr)

    # Build LangGraph
    try:
        graph = _build_graph(
            llm, grammar,
            args.locationiq_key,
            voyage_client, args.voyage_model,
            chroma_col, output_dir,
            force=args.force,
        )
        print("LangGraph ready. Tagging...\n", flush=True)
    except ImportError:
        sys.exit("[ERROR] langgraph not installed.\n  py -3.11 -m pip install langgraph")

    # Start producer thread (CPU preprocessing runs in parallel with GPU inference)
    q: queue.Queue = queue.Queue(maxsize=3)
    producer = threading.Thread(target=_producer, args=(files, q), daemon=True)
    producer.start()

    results: List[TagResult] = []
    done = 0

    while True:
        item = q.get()
        if item is _SENTINEL:
            break

        path, b64, (gps_lat, gps_lon), capture_datetime, context = item
        done += 1
        print(f"  [{done}/{len(files)}] {path.name}", end=" ", flush=True)

        final: ImageState = graph.invoke(ImageState(
            path=path,
            b64=b64,
            gps_lat=gps_lat,
            gps_lon=gps_lon,
            capture_datetime=capture_datetime,
            context=context,
            scene="",
            time_of_day="",
            activity="",
            weather_condition="",
            mood="",
            aesthetic_score=0,
            has_identifiable_faces=False,
            objects=[],
            attributes=[],
            caption="",
            retry_count=0,
            geo=GeoInfo(),
            photo_id="",
            file_path="",
            season="",
            location_confidence="",
            retrieval_text="",
            multimodal_embedding=[],
            error="",
        ))

        r = _state_to_tagresult(final)
        results.append(r)

        if r.error:
            print(f"→ error: {r.error[:60]}", flush=True)
        else:
            status = f"→ {r.scene}"
            if final["retry_count"] > 1:
                status += " (retried)"
            if r.geo.city:
                status += f"  [{r.geo.city}, {r.geo.country}]"
            status += f"  aesthetic:{r.aesthetic_score}"
            if r.location_confidence in ("low", "medium"):
                status += f"  [loc:{r.location_confidence}]"
            if r.has_identifiable_faces:
                status += "  [faces-flagged]"
            if r.multimodal_embedding:
                status += "  [embedded]"
            print(status, flush=True)

    producer.join()

    csv_path = output_dir / "summary.csv"
    _write_csv(results, csv_path)

    ok            = sum(1 for r in results if not r.error)
    blurry        = sum(1 for r in results if r.error and r.error.startswith("blurry"))
    already_done  = sum(1 for r in results if r.error == "already_processed")
    retried       = sum(1 for r in results if r.retry_count > 1)
    embedded      = sum(1 for r in results if r.multimodal_embedding)
    face_flagged  = sum(1 for r in results if r.has_identifiable_faces)
    indexed       = sum(
        1 for r in results
        if r.photo_id and chroma_col and not r.error
        and r.aesthetic_score >= 6 and not r.has_identifiable_faces
    )
    print(
        f"\n✓ {ok}/{len(files)} tagged"
        f"  |  {already_done} skipped (already done)"
        f"  |  {blurry} blurry-skipped"
        f"  |  {retried} retried"
        f"  |  {embedded} embedded"
        f"  |  {indexed} indexed (blog-ready)"
        f"  |  {face_flagged} face-flagged"
        f"  |  summary → {csv_path}"
    )


if __name__ == "__main__":
    main()
