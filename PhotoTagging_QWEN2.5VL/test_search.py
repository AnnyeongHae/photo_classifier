"""
ChromaDB photo search CLI — travel RAG pipeline companion.

Queries the travel_photos (Voyage multimodal) or travel_photos_text (ChromaDB
auto-embed) collection and displays ranked results with score, metadata preview,
and a truncated retrieval_text.

Usage:
    py -3.11 test_search.py "serene beach at golden hour"
    py -3.11 test_search.py "accommodation in Patagonia" --n 5 --scene accommodation
    py -3.11 test_search.py "dramatic mountain landscape" --mood dramatic --country Chile
    py -3.11 test_search.py "cozy cafe morning" --aesthetic-min 7 --no-faces
    py -3.11 test_search.py "wildlife in Africa" --season summer --voyage-key pa-xxx

Required:
    chromadb    — pip install chromadb
    voyageai    — pip install voyageai   (only if you used --voyage-key during tagging)
"""
# -*- coding: utf-8 -*-
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── .env loader ───────────────────────────────────────────────────────────────

_HERE = Path(__file__).parent


def _load_dotenv(env_path: Path) -> None:
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_where(
    scene: Optional[str],
    country: Optional[str],
    mood: Optional[str],
    season: Optional[str],
    aesthetic_min: Optional[int],
    no_faces: bool,
) -> Optional[Dict]:
    """Build a ChromaDB $and where-filter from CLI flags.
    Returns None if no filters were specified (avoids sending empty $and)."""
    conditions: List[Dict] = []
    if scene:
        conditions.append({"scene": {"$eq": scene}})
    if country:
        conditions.append({"geo_country": {"$eq": country}})
    if mood:
        conditions.append({"mood": {"$eq": mood}})
    if season:
        conditions.append({"season": {"$eq": season}})
    if aesthetic_min is not None:
        conditions.append({"aesthetic_score": {"$gte": aesthetic_min}})
    if no_faces:
        conditions.append({"has_identifiable_faces": {"$eq": False}})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def _embed_voyage(text: str, client: Any, model: str) -> Optional[List[float]]:
    """Embed a text query using Voyage multimodal API (text-only input)."""
    try:
        result = client.multimodal_embed(
            inputs=[[text]],
            model=model,
            input_type="query",
        )
        return result.embeddings[0]
    except Exception as e:
        print(f"[voyage embed error] {e}", file=sys.stderr)
        return None


def _fmt_score(distance: float) -> str:
    """Convert cosine distance → similarity score string."""
    # ChromaDB returns cosine distance (0=identical, 2=opposite) for cosine space
    similarity = 1.0 - distance
    return f"{similarity:.3f}"


def _truncate(text: str, max_len: int = 140) -> str:
    return text if len(text) <= max_len else text[:max_len - 3] + "..."


def _print_result(rank: int, doc_id: str, distance: float, document: str, meta: Dict) -> None:
    score = _fmt_score(distance)
    scene   = meta.get("scene", "")
    mood    = meta.get("mood", "")
    season  = meta.get("season", "")
    tod     = meta.get("time_of_day", "")
    city    = meta.get("geo_city", "")
    country = meta.get("geo_country", "")
    aesth   = meta.get("aesthetic_score", "")
    faces   = meta.get("has_identifiable_faces", False)
    fpath   = meta.get("file_path") or meta.get("file", "")
    dt      = meta.get("capture_datetime", "")[:10]

    loc_parts = [p for p in [city, country] if p]
    loc_str   = ", ".join(loc_parts) if loc_parts else "—"

    tags = [scene, tod]
    if mood:
        tags.append(mood)
    if season:
        tags.append(season)

    print(f"\n{'─'*72}")
    print(f"  #{rank:2d}  score={score}   [{' | '.join(t for t in tags if t)}]")
    print(f"       aesthetic:{aesth}  faces:{faces}  date:{dt or '—'}  loc:{loc_str}")
    print(f"       {_truncate(document)}")
    if fpath:
        print(f"       ↳ {fpath}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    _load_dotenv(_HERE / ".env")

    parser = argparse.ArgumentParser(
        description="Search the travel photo ChromaDB index",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("query", help="Natural language search query")
    parser.add_argument("--n",            type=int, default=5,   help="Number of results (default: 5)")
    parser.add_argument("--voyage-key",   default=os.environ.get("VOYAGE_API_KEY", ""),
                        help="Voyage AI API key (reads VOYAGE_API_KEY from .env)")
    parser.add_argument("--voyage-model", default="voyage-multimodal-3",
                        help="Voyage model used during indexing (must match)")
    parser.add_argument("--chromadb",     default=str(_HERE / "chroma_db"),
                        help="ChromaDB directory (default: ./chroma_db)")
    # Metadata filters
    parser.add_argument("--scene",    help="Filter by scene  (e.g. accommodation, beach, landscape)")
    parser.add_argument("--country",  help="Filter by geo_country (e.g. Chile, Japan)")
    parser.add_argument("--mood",     help="Filter by mood  (e.g. serene, dramatic, vibrant)")
    parser.add_argument("--season",   help="Filter by season (spring/summer/autumn/winter)")
    parser.add_argument("--aesthetic-min", type=int, metavar="N",
                        help="Minimum aesthetic_score (e.g. 7)")
    parser.add_argument("--no-faces", action="store_true",
                        help="Exclude photos with identifiable faces")
    args = parser.parse_args()

    # ── Load ChromaDB ─────────────────────────────────────────────────────────
    try:
        import chromadb
    except ImportError:
        sys.exit("[ERROR] chromadb not installed.  pip install chromadb")

    db_path = Path(args.chromadb)
    if not db_path.exists():
        sys.exit(f"[ERROR] ChromaDB directory not found: {db_path}\n"
                 f"Run test_tagger.py with --chromadb to build the index first.")

    client = chromadb.PersistentClient(path=str(db_path))

    # Auto-detect collection: prefer Voyage (multimodal) over text-only
    available = [c.name for c in client.list_collections()]
    if not available:
        sys.exit("[ERROR] No collections found in the ChromaDB. Run test_tagger.py first.")

    voyage_col_name = "travel_photos"
    text_col_name   = "travel_photos_text"

    if voyage_col_name in available:
        col = client.get_collection(voyage_col_name)
        use_voyage = True
    elif text_col_name in available:
        col = client.get_collection(text_col_name)
        use_voyage = False
    else:
        # Fall back to whatever collection exists
        col = client.get_collection(available[0])
        use_voyage = False

    total = col.count()
    if total == 0:
        sys.exit("[ERROR] Collection is empty. Run test_tagger.py to index some photos.")

    print(f"Collection : '{col.name}'  ({total} documents)", flush=True)

    # ── Build metadata where-filter ───────────────────────────────────────────
    where = _build_where(
        scene=args.scene,
        country=args.country,
        mood=args.mood,
        season=args.season,
        aesthetic_min=args.aesthetic_min,
        no_faces=args.no_faces,
    )
    if where:
        print(f"Filters    : {json.dumps(where)}", flush=True)

    # ── Embed query (Voyage) or text search (ChromaDB auto) ───────────────────
    query_embedding: Optional[List[float]] = None

    if use_voyage:
        if not args.voyage_key:
            print("[warn] Voyage collection found but no --voyage-key provided.\n"
                  "       Falling back to text search (lower accuracy).", file=sys.stderr)
        else:
            try:
                import voyageai
                voyage_client = voyageai.Client(api_key=args.voyage_key)
                query_embedding = _embed_voyage(args.query, voyage_client, args.voyage_model)
            except ImportError:
                print("[warn] voyageai not installed — pip install voyageai", file=sys.stderr)

    # ── Query ChromaDB ────────────────────────────────────────────────────────
    n_results = min(args.n, total)
    query_kwargs: Dict[str, Any] = {
        "n_results":        n_results,
        "include":          ["documents", "metadatas", "distances"],
    }
    if where:
        query_kwargs["where"] = where

    try:
        if query_embedding:
            results = col.query(query_embeddings=[query_embedding], **query_kwargs)
            search_mode = f"multimodal (voyage {args.voyage_model})"
        else:
            results = col.query(query_texts=[args.query], **query_kwargs)
            search_mode = "text (ChromaDB default embeddings)"
    except Exception as e:
        sys.exit(f"[ERROR] ChromaDB query failed: {e}")

    # ── Display results ───────────────────────────────────────────────────────
    ids        = results["ids"][0]
    documents  = results["documents"][0]
    metadatas  = results["metadatas"][0]
    distances  = results["distances"][0]

    print(f"\nQuery      : \"{args.query}\"")
    print(f"Search mode: {search_mode}")
    print(f"Results    : {len(ids)} of {total} total")

    if not ids:
        print("\n(no results — try relaxing your filters or broadening the query)")
        return

    for i, (doc_id, dist, doc, meta) in enumerate(
        zip(ids, distances, documents, metadatas), start=1
    ):
        _print_result(i, doc_id, dist, doc, meta)

    print(f"\n{'─'*72}")
    print(f"  Tip: use --scene / --mood / --season / --country / --aesthetic-min / --no-faces to narrow results.")


if __name__ == "__main__":
    main()
