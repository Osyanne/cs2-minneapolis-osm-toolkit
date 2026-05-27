"""
transporte/extract.py — Transit route extractor for CS2 OSM Toolkit
====================================================================
Pipeline:
  1. Query Overpass for route=* relations in city bbox
  2. For each relation: extract member way geometries → concatenate into LineStrings
  3. Classify by tags (LRT / Commuter / BRT / Bus)
  4. Emit visualizer/cities/<slug>/datos_transporte.js

CLI:
  cd src && uv run extract-transporte --city minneapolis
"""
from __future__ import annotations


def extract_way_geoms(relation: dict) -> list[list[list[float]]]:
    """Extract LineString geometries from way members of a relation.

    Each way member is converted to [[lat, lon], ...] form. Node members
    (typically stops/platforms) are skipped. Ways without geometry or with
    empty geometry are skipped.

    Args:
        relation: Overpass JSON relation element.

    Returns:
        List of LineStrings (each is a list of [lat, lon] pairs).
    """
    members = relation.get("members") or []
    out: list[list[list[float]]] = []
    for m in members:
        if m.get("type") != "way":
            continue
        geom = m.get("geometry") or []
        if not geom:
            continue
        out.append([[pt["lat"], pt["lon"]] for pt in geom])
    return out


def concatenate_ways(ways: list[list[list[float]]]) -> list[list[list[float]]]:
    """Concatenate adjacent way LineStrings into continuous segments.

    Two consecutive ways are merged if their endpoints touch (in any direction).
    If they don't touch, a new segment starts. Result is the minimal list of
    continuous LineStrings needed to represent the input.

    Args:
        ways: List of LineStrings (each is a list of [lat, lon] pairs).

    Returns:
        List of merged LineStrings. Empty list if input is empty.
    """
    if not ways:
        return []
    segments: list[list[list[float]]] = [list(ways[0])]
    for w in ways[1:]:
        if not w:
            continue
        current = segments[-1]
        current_end = current[-1]
        w_start = w[0]
        w_end = w[-1]
        if current_end == w_start:
            # tail-to-head: append all but first point of w
            current.extend(w[1:])
        elif current_end == w_end:
            # tail-to-tail: reverse w then append all but first
            reversed_w = list(reversed(w))
            current.extend(reversed_w[1:])
        else:
            # gap — start a new segment
            segments.append(list(w))
    return segments


COORD_PRECISION = 5  # 5 decimals ≈ 1.1m at the equator


def _round_coords(coords: list[list[float]]) -> list[list[float]]:
    return [[round(lat, COORD_PRECISION), round(lon, COORD_PRECISION)] for lat, lon in coords]


def build_route_feature(relation: dict, cs2_key: str) -> dict | None:
    """Convert an Overpass relation element to a feature dict.

    Args:
        relation: Overpass JSON relation element.
        cs2_key: CS2 category from classify_route().

    Returns:
        dict with keys: name, ref, coords, operator, osm_id — or None if no
        usable geometry (no member ways with coords). If the relation has
        multiple disjoint segments, only the longest one is kept in coords.
    """
    way_geoms = extract_way_geoms(relation)
    if not way_geoms:
        return None
    segments = concatenate_ways(way_geoms)
    if not segments:
        return None
    longest = max(segments, key=len)
    if len(longest) < 2:
        return None

    tags = relation.get("tags") or {}
    name = tags.get("name") or ""
    ref = tags.get("ref") or ""
    if not name:
        name = f"Route {ref}" if ref else "Unknown route"

    return {
        "name": name,
        "ref": ref,
        "coords": _round_coords(longest),
        "operator": tags.get("operator") or "",
        "osm_id": relation.get("id"),
    }


# ──────────────────────────────────────────────────────────────────────────
# CLI + main pipeline
# ──────────────────────────────────────────────────────────────────────────

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from shared.overpass_client import query_with_retry
from shared.registry import (
    load_cities,
    get_city,
    CityNotFoundError,
    RegistryError,
    save_manifest_entry,
)
from transporte.classifiers import classify_route
from transporte.zones import TRANSPORT_LABELS, build_transporte_query


def resolve_city_args(
    city: str | None,
    bbox: str | None,
    slug: str | None,
    cities_file: Path,
) -> tuple[str, str]:
    """Resolve --city or --bbox+--slug to (bbox_str, slug)."""
    if city is not None:
        if bbox is not None:
            print(
                f"[WARNING] Ignoring --bbox '{bbox}' because --city='{city}' takes priority.",
                file=sys.stderr,
            )
        cities = load_cities(cities_file)
        entry = get_city(cities, city)
        s, w, n, e = entry["bbox"]
        return (f"{s},{w},{n},{e}", city)
    if bbox is not None:
        if slug is None:
            raise ValueError("If you pass --bbox you must also pass --slug")
        return (bbox, slug)
    raise ValueError("You must pass --city or --bbox+--slug")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract OSM transit routes → JS prebuilt")
    parser.add_argument("--city", help="City slug from cities.json (e.g. minneapolis)")
    parser.add_argument("--bbox", help="Escape hatch: bbox 's,w,n,e' (requires --slug)")
    parser.add_argument("--slug", help="Output slug when using --bbox without --city")
    parser.add_argument("--cities-file", default=None,
                        help="Path to cities.json (default: <repo_root>/cities.json)")
    parser.add_argument("--visualizer-root", default=None,
                        help="Path to visualizer/ (default: <repo_root>/visualizer)")
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    cities_file = Path(args.cities_file) if args.cities_file else repo_root / "cities.json"
    vis_root = Path(args.visualizer_root) if args.visualizer_root else repo_root / "visualizer"

    try:
        bbox, slug = resolve_city_args(args.city, args.bbox, args.slug, cities_file)
    except (CityNotFoundError, RegistryError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    out_dir = vis_root / "cities" / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "datos_transporte.js"

    print(f"CS2 OSM Toolkit — Transporte Extractor")
    print(f"City         : {slug}")
    print(f"Bounding Box : {bbox}")
    print(f"Output       : {out_path}\n")

    query = build_transporte_query(bbox)
    print("[1/2] Downloading transit relations from Overpass…")
    result = query_with_retry(query, "transporte")
    elements = result.get("elements", [])
    print(f"      raw relations: {len(elements)}")

    print("\n[2/2] Classifying + building features…")
    buckets: dict[str, list] = defaultdict(list)
    skipped_class = 0
    skipped_geom = 0

    for el in elements:
        if el.get("type") != "relation":
            continue
        cs2_key = classify_route(el.get("tags") or {})
        if cs2_key is None:
            skipped_class += 1
            continue
        feat = build_route_feature(el, cs2_key)
        if feat is None:
            skipped_geom += 1
            continue
        buckets[cs2_key].append(feat)

    total = sum(len(v) for v in buckets.values())

    print()
    print(f"  {'category':<10}  count")
    print(f"  {'-'*10}  {'-'*5}")
    for key in TRANSPORT_LABELS:
        n = len(buckets.get(key, []))
        print(f"  {key:<10}  {n:>5}")
    print(f"  {'-'*10}  {'-'*5}")
    print(f"  {'TOTAL':<10}  {total:>5}")
    print(f"\n  skipped (no classifier): {skipped_class}")
    print(f"  skipped (no geometry):   {skipped_geom}")

    ts = datetime.now(timezone.utc).isoformat()
    with out_path.open("w", encoding="utf-8") as f:
        f.write(f"// Auto-generated by transporte.extract — {ts}\n")
        f.write(f"// {slug} — Transporte — bbox: {bbox}\n")
        f.write(f"// Source: OpenStreetMap (Overpass query route=*)\n")
        f.write(f"// Total routes: {total}\n\n")
        for key in TRANSPORT_LABELS:
            features = buckets.get(key, [])
            var_name = f"DATA_TRANSPORT_{key.upper()}"
            f.write(f"var {var_name} = ")
            json.dump(features, f, ensure_ascii=False, separators=(",", ":"))
            f.write(";\n")

    size_kb = out_path.stat().st_size / 1024
    print(f"\nDone. {out_path} — {size_kb:.1f} KB — {total} features")

    save_manifest_entry(
        visualizer_root=vis_root,
        slug=slug,
        module="transporte",
        file_path=out_path,
        features=total,
    )
    print(f"Manifest      : {vis_root / 'cities' / slug / 'manifest.json'}")


if __name__ == "__main__":
    main()
