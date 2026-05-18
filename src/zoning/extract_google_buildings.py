#!/usr/bin/env python3
"""
extract_google_buildings.py — Augment with Google Open Buildings v3
====================================================================
v3.3.5 — Para ciudades con cobertura OSM sparse (LATAM small-town, África,
SE-Asia), agrega building footprints ML-detectados de Google Open Buildings
v3 y los clasifica con el mismo algoritmo de v3.3.4 (spatial join landuse +
heurística de área).

Pipeline:
  1. Determine S2 level-6 cells covering the city bbox (vía s2sphere).
  2. Download those cells from Google's public GCS bucket (cached en .cache/).
  3. Fetch landuse polygons (residential/commercial/retail/industrial/office)
     desde OSM via Overpass para construir el spatial join index.
  4. Stream-parse cada CSV.gz, filtrar por bbox + confidence ≥ threshold.
  5. Para cada Google building: spatial join contra landuse, fallback heurística
     por área (algoritmo idéntico al de extract-zoning v3.3.4).
  6. Output: visualizer/cities/<slug>/datos_external_buildings.js con
     `DATA_EXT_<ZONE>` arrays paralelos a los DATA_<ZONE> de zoning.
  7. Manifest: añade entry `external_buildings` con hash + features count.

Uso:
    cd src
    uv run extract-google-buildings --city mafra_sc_brazil
    uv run extract-google-buildings --city mafra_sc_brazil --min-confidence 0.80
"""

import argparse
import csv
import gzip
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests
import s2sphere
from shapely.geometry import Polygon
from shapely.strtree import STRtree
from shapely.wkt import loads as wkt_loads

from shared.overpass_client import query_with_retry
from shared.registry import (
    load_cities,
    get_city,
    save_manifest_entry,
    CityNotFoundError,
    RegistryError,
)
from zoning.classifiers import (
    classify_generic_building_by_area,
    is_civic_amenity_tag,
    LANDUSE_TO_CS2_KEY,
)
from zoning.zones import CS2_LABELS, build_queries


OPEN_BUILDINGS_BASE = (
    "https://storage.googleapis.com/open-buildings-data/v3/"
    "polygons_s2_level_6_gzip_no_header"
)
DEFAULT_MIN_CONFIDENCE = 0.75


# ── Cache helpers ────────────────────────────────────────────────────────────

def get_cache_dir() -> Path:
    """Local cache (repo-relative, gitignored via .cache/)."""
    repo_root = Path(__file__).resolve().parents[2]
    cache = repo_root / ".cache" / "google_open_buildings"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


# ── S2 cell computation ──────────────────────────────────────────────────────

def s2_cells_for_bbox(bbox: list) -> list[str]:
    """
    Devuelve los tokens S2 L6 que tocan el bbox.

    L6 cells son grandes (~50,000–100,000 km² cada uno) — un bbox típico de
    ciudad cae dentro de 1 cell. Solo bboxes en bordes de cell tocan 2+.
    """
    s, w, n, e = bbox
    tokens: set[str] = set()
    # 4 esquinas + centroide; cubre cualquier bbox razonable
    sample_points = [
        (s, w), (s, e), (n, w), (n, e),
        ((s + n) / 2, (w + e) / 2),
    ]
    for lat, lon in sample_points:
        ll = s2sphere.LatLng.from_degrees(lat, lon)
        cell = s2sphere.CellId.from_lat_lng(ll).parent(6)
        tokens.add(cell.to_token())
    return sorted(tokens)


# ── Download ─────────────────────────────────────────────────────────────────

def download_cell(token: str, cache: Path) -> Path:
    """
    Descarga (idempotente) un S2 L6 cell CSV.gz de Google Open Buildings.

    Files típicos: 50–500 MB compressed. Una vez en cache, sucesivos runs son
    instantáneos.
    """
    local = cache / f"{token}_buildings.csv.gz"
    if local.exists() and local.stat().st_size > 1_000_000:
        size_mb = local.stat().st_size / (1024 * 1024)
        print(f"  cached: {local.name} ({size_mb:.1f} MB)")
        return local

    url = f"{OPEN_BUILDINGS_BASE}/{token}_buildings.csv.gz"
    print(f"  downloading: {url}")
    with requests.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        next_report_at = 25 * 1024 * 1024  # report cada 25 MB
        with open(local, "wb") as f:
            for chunk in r.iter_content(chunk_size=131_072):
                f.write(chunk)
                downloaded += len(chunk)
                if downloaded >= next_report_at and total > 0:
                    pct = downloaded / total * 100
                    print(
                        f"    {downloaded / (1024*1024):.0f}/"
                        f"{total / (1024*1024):.0f} MB ({pct:.0f}%)"
                    )
                    next_report_at += 25 * 1024 * 1024
    size_mb = local.stat().st_size / (1024 * 1024)
    print(f"  saved: {local.name} ({size_mb:.1f} MB)")
    return local


# ── Landuse polygon extraction (OSM via Overpass) ────────────────────────────

def _coords_from_element(el: dict) -> list | None:
    """Extrae [(lon, lat), ...] para construir shapely Polygon."""
    if el.get("type") == "way":
        geom = el.get("geometry", [])
        if len(geom) < 3:
            return None
        return [(pt["lon"], pt["lat"]) for pt in geom]
    if el.get("type") == "relation":
        members = el.get("members", [])
        outers = [
            m for m in members
            if m.get("role") == "outer" and len(m.get("geometry", [])) > 2
        ]
        if not outers:
            return None
        outers.sort(key=lambda m: len(m["geometry"]), reverse=True)
        return [(pt["lon"], pt["lat"]) for pt in outers[0]["geometry"]]
    return None


def _make_polygon(coords) -> Polygon | None:
    """Crear shapely.Polygon validado o None."""
    try:
        p = Polygon(coords)
        if p.is_valid and not p.is_empty:
            return p
    except Exception:
        return None
    return None


def fetch_civic_amenities(bbox_str: str) -> list:
    """
    Pulls civic amenity nodes (school/hospital/church/etc.) via Overpass.
    Returns list of shapely.Point (lon, lat) — usado para amenity cross-reference.
    """
    from shapely.geometry import Point as _ShapelyPoint
    queries = build_queries(bbox_str)
    if "civic_amenities" not in queries:
        return []
    print("  fetching civic_amenities...")
    result = query_with_retry(queries["civic_amenities"], "civic_amenities")
    points = []
    for el in result.get("elements", []):
        if el.get("type") != "node":
            continue
        lat = el.get("lat")
        lon = el.get("lon")
        if lat is None or lon is None:
            continue
        points.append(_ShapelyPoint(lon, lat))
    return points


def fetch_landuse_polygons(bbox_str: str) -> list[tuple[Polygon, str]]:
    """
    Pulls landuse polygons from OSM (4 queries) y devuelve lista
    (shapely.Polygon, cs2_key) para spatial join.

    Reusa el mismo set de queries que zoning.zones.build_queries para
    consistencia con extract-zoning.
    """
    queries = build_queries(bbox_str)
    polys: list[tuple[Polygon, str]] = []

    pipelines = [
        ("landuse_residential", lambda tags: "res_low_house"),
        ("commercial", lambda tags: LANDUSE_TO_CS2_KEY.get(
            (tags.get("landuse") or "").lower()
        )),
        ("industrial", lambda tags: LANDUSE_TO_CS2_KEY.get(
            (tags.get("landuse") or "").lower()
        )),
        ("office", lambda tags: LANDUSE_TO_CS2_KEY.get(
            (tags.get("landuse") or "").lower()
        )),
    ]

    for query_key, key_fn in pipelines:
        print(f"  fetching {query_key}...")
        result = query_with_retry(queries[query_key], query_key)
        for el in result.get("elements", []):
            cs2_key = key_fn(el.get("tags") or {})
            if cs2_key is None:
                continue
            coords = _coords_from_element(el)
            if not coords:
                continue
            poly = _make_polygon(coords)
            if poly is not None:
                polys.append((poly, cs2_key))

    return polys


# ── Classification (mismo algoritmo que extract.py paso 8) ───────────────────

def classify_building(
    poly: Polygon,
    area_m2: float,
    tree: STRtree | None,
    landuse_geoms: list,
    landuse_keys: list,
    amenity_tree: STRtree | None = None,
    amenity_points: list | None = None,
) -> tuple[str, str]:
    """
    Returns (cs2_key, method) donde method ∈ {"landuse", "area", "amenity"}.
    Algoritmo idéntico a _process_generic_buildings en zoning.extract.
    """
    if tree is not None:
        try:
            centroid = poly.centroid
            candidates = tree.query(centroid)
            for cand in candidates:
                if hasattr(cand, "__index__"):
                    idx = int(cand)
                    if landuse_geoms[idx].contains(centroid):
                        return (landuse_keys[idx], "landuse")
        except Exception:
            pass
    # Sin landuse match: heurística de área pura, pero antes verifica amenity proximity.
    if amenity_tree is not None and amenity_points is not None:
        if _has_civic_amenity_near_pt(poly.centroid, amenity_tree, amenity_points, max_dist_m=30.0):
            return ("com_low", "amenity")
    return (classify_generic_building_by_area(area_m2), "area")


def _has_civic_amenity_near_pt(
    centroid,
    amenity_tree: STRtree,
    amenity_points: list,
    max_dist_m: float = 30.0,
) -> bool:
    """
    Misma lógica que _has_civic_amenity_near en zoning.extract — duplicada
    porque las dependencias cruzadas entre los extractors complicarían el import.
    """
    import math
    lat0 = centroid.y
    cos_lat = math.cos(math.radians(lat0))
    deg_per_m_lat = 1.0 / 111_320.0
    deg_per_m_lon = 1.0 / (111_320.0 * max(cos_lat, 0.01))
    buf_lat = deg_per_m_lat * max_dist_m
    buf_lon = deg_per_m_lon * max_dist_m
    from shapely.geometry import box
    bbox = (
        centroid.x - buf_lon, centroid.y - buf_lat,
        centroid.x + buf_lon, centroid.y + buf_lat,
    )
    candidates = amenity_tree.query(box(*bbox))
    for cand in candidates:
        if hasattr(cand, "__index__"):
            pt = amenity_points[int(cand)]
        else:
            pt = cand
        dx_m = (pt.x - centroid.x) * 111_320.0 * cos_lat
        dy_m = (pt.y - centroid.y) * 111_320.0
        if (dx_m * dx_m + dy_m * dy_m) <= (max_dist_m * max_dist_m):
            return True
    return False


# ── Streaming + classification ───────────────────────────────────────────────

def stream_classify_csv(
    csv_gz_path: Path,
    bbox: list,
    min_confidence: float,
    tree: STRtree | None,
    landuse_geoms: list,
    landuse_keys: list,
    output: dict,
    starting_id: int,
    amenity_tree: STRtree | None = None,
    amenity_points: list | None = None,
) -> tuple[int, int, int, int]:
    """
    Stream-parse CSV.gz, filter por bbox + confidence, classify, append a output.

    Cada row del CSV (sin header) tiene columnas:
        latitude,longitude,area_in_meters,confidence,geometry,full_plus_code

    Returns (added_count, by_landuse, by_area, by_amenity).
    """
    south, west, north, east = bbox
    by_landuse = 0
    by_area = 0
    by_amenity = 0
    added = 0
    next_id = starting_id

    with gzip.open(csv_gz_path, "rt", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 5:
                continue
            try:
                lat = float(row[0])
                lon = float(row[1])
                area_m2 = float(row[2])
                conf = float(row[3])
            except (ValueError, IndexError):
                continue
            if not (south <= lat <= north and west <= lon <= east):
                continue
            if conf < min_confidence:
                continue
            try:
                poly = wkt_loads(row[4])
            except Exception:
                continue
            if not poly.is_valid or poly.is_empty:
                continue

            cs2_key, method = classify_building(
                poly, area_m2, tree, landuse_geoms, landuse_keys,
                amenity_tree=amenity_tree, amenity_points=amenity_points,
            )
            if method == "landuse":
                by_landuse += 1
            elif method == "amenity":
                by_amenity += 1
            else:
                by_area += 1

            try:
                coords_latlon = [[y, x] for x, y in poly.exterior.coords]
            except Exception:
                continue

            output[cs2_key].append({
                "id": f"g{next_id}",
                "name": "",
                "coords": coords_latlon,
                "cs2_key": cs2_key,
                "cs2": CS2_LABELS.get(cs2_key, cs2_key),
                "src": "google",
                "conf": round(conf, 2),
                "method": method,  # "landuse" | "area" — para visualizer encoding
            })
            next_id += 1
            added += 1

    return (added, by_landuse, by_area, by_amenity)


# ── Main pipeline ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Augment city zoning with Google Open Buildings v3 ML footprints"
    )
    parser.add_argument(
        "--city", required=True,
        help="Slug del registro (cities.json)",
    )
    parser.add_argument(
        "--min-confidence", type=float, default=DEFAULT_MIN_CONFIDENCE,
        help=f"Filtro mínimo de confidence (default {DEFAULT_MIN_CONFIDENCE})",
    )
    parser.add_argument(
        "--cities-file", default=None,
        help="Path a cities.json (default: <repo>/cities.json)",
    )
    parser.add_argument(
        "--visualizer-root", default=None,
        help="Path a visualizer/ (default: <repo>/visualizer)",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    cities_file = Path(args.cities_file) if args.cities_file else repo_root / "cities.json"
    vis_root = Path(args.visualizer_root) if args.visualizer_root else repo_root / "visualizer"

    try:
        cities = load_cities(cities_file)
        entry = get_city(cities, args.city)
    except (CityNotFoundError, RegistryError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    bbox = entry["bbox"]
    bbox_str = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"

    out_dir = vis_root / "cities" / args.city
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "datos_external_buildings.js"

    print("Google Open Buildings v3 — Augmentation")
    print(f"City        : {args.city}")
    print(f"Bbox        : {bbox_str}")
    print(f"Min conf    : {args.min_confidence}")
    print(f"Output      : {out_path}\n")

    # 1. S2 cells
    cells = s2_cells_for_bbox(bbox)
    print(f"[1/4] S2 L6 cells covering bbox: {cells}")

    # 2. Download (cached)
    cache = get_cache_dir()
    print(f"\n[2/4] Downloading cells (cache: {cache})...")
    cell_paths = [download_cell(token, cache) for token in cells]

    # 3. Landuse polygons + civic amenities (Overpass)
    print(f"\n[3/4] Fetching landuse polygons + civic amenities from OSM...")
    landuse_polys = fetch_landuse_polygons(bbox_str)
    print(f"      {len(landuse_polys)} landuse polygons total")
    landuse_geoms = [lp[0] for lp in landuse_polys]
    landuse_keys = [lp[1] for lp in landuse_polys]
    tree = STRtree(landuse_geoms) if landuse_geoms else None

    amenity_points = fetch_civic_amenities(bbox_str)
    print(f"      {len(amenity_points)} civic amenity nodes")
    amenity_tree = STRtree(amenity_points) if amenity_points else None

    # 4. Stream + classify
    print(f"\n[4/4] Streaming Google buildings + classifying...")
    output: dict[str, list] = defaultdict(list)
    total_added = 0
    total_by_landuse = 0
    total_by_area = 0
    total_by_amenity = 0
    for path in cell_paths:
        print(f"  processing {path.name}...")
        added, by_landuse, by_area, by_amenity = stream_classify_csv(
            path, bbox, args.min_confidence,
            tree, landuse_geoms, landuse_keys,
            output, starting_id=total_added,
            amenity_tree=amenity_tree, amenity_points=amenity_points,
        )
        print(
            f"    +{added} buildings "
            f"(landuse: {by_landuse}, area: {by_area}, "
            f"amenity-override: {by_amenity})"
        )
        total_added += added
        total_by_landuse += by_landuse
        total_by_area += by_area
        total_by_amenity += by_amenity

    # Summary
    total = sum(len(v) for v in output.values())
    print()
    for key in CS2_LABELS:
        print(f"  {key:<16}: {len(output.get(key, [])):>6}  ({CS2_LABELS[key]})")
    print(f"  {'TOTAL':<16}: {total:>6}")
    print(f"  classified by landuse:        {total_by_landuse}")
    print(f"  classified by area:           {total_by_area}")
    print(f"  reclassified by amenity:      {total_by_amenity}")

    # Write output
    ts = datetime.now(timezone.utc).isoformat()
    lines = [
        f"// Auto-generated by extract_google_buildings.py — {ts}",
        f"// {args.city} — Google Open Buildings v3 augmentation",
        f"// Bbox: {bbox_str}",
        f"// Min confidence: {args.min_confidence}",
        f"// Total buildings: {total}  (landuse: {total_by_landuse}, area: {total_by_area}, amenity-override: {total_by_amenity})",
        f"// S2 cells: {','.join(cells)}",
        "",
    ]
    for key in CS2_LABELS:
        var = f"DATA_EXT_{key.upper()}"
        lines.append(f"const {var} = {json.dumps(output.get(key, []))};")
    out_path.write_text("\n".join(lines), encoding="utf-8")

    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"\nDone. {out_path} — {size_mb:.1f} MB — {total} buildings")

    # Update manifest
    save_manifest_entry(
        visualizer_root=vis_root,
        slug=args.city,
        module="external_buildings",
        file_path=out_path,
        features=total,
    )
    print(f"Manifest    : {vis_root / 'cities' / args.city / 'manifest.json'}")


if __name__ == "__main__":
    main()
