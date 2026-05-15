#!/usr/bin/env python3
"""
extract_msbuildings.py — Augment OSM data with Microsoft Building Footprints
============================================================================

Sesión 1.8 — Llena los gaps de OSM con buildings detectados por satélite por
Microsoft. Source: https://github.com/microsoft/USBuildingFootprints

Pipeline:
  1. Lee datos_zonificacion.js para extraer:
       - Landuse polygons OSM (residential, commercial, industrial, office)
         → para clasificar cada building MS por la zona que lo contiene
       - Building polygons OSM existentes → para deduplicar
  2. Descarga Microsoft USBuildingFootprints/Minnesota.geojson.zip si no está cacheado
  3. Stream-parsea el GeoJSON (5M features), filtra a bbox de Mineapolis
  4. Para cada building MS:
       a) Skip si ya hay un building OSM cerca (≤5m del centroide)
       b) Clasifica por landuse OSM que lo contiene
       c) Si no hay match de landuse → skip
  5. Output: datos_msbuildings.js con buildings clasificados por zona CS2

Uso:
    cd src
    uv run extract_msbuildings.py
    uv run extract_msbuildings.py --bbox "44.86,-93.38,45.05,-93.17"

El visualizer detecta automáticamente datos_msbuildings.js y lo carga si existe.
Para rollback: borrar visualizer/datos_msbuildings.js.
"""

import argparse
import io
import json
import math
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests
from shapely.geometry import Polygon, Point, shape
from shapely.strtree import STRtree


# ── Config ──────────────────────────────────────────────────────────────────

MS_BUILDINGS_URL = (
    "https://minedbuildings.z5.web.core.windows.net/legacy/usbuildings-v2/Minnesota.geojson.zip"
)
DEFAULT_BBOX = "44.86,-93.38,45.05,-93.17"
DEDUP_RADIUS_M = 5.0  # Si hay un building OSM a ≤5m del centroide MS, skip
COORD_PRECISION = 6   # 6 decimales = ~10cm — suficiente para visualización

# Clasificación por landuse OSM que contiene el building MS
LANDUSE_TO_CS2 = {
    "residential": "res_low_house",
    "commercial":  "com_low",
    "retail":      "com_low",
    "industrial":  "industrial",
    "office":      "office_low",
}


# ── Parsing datos_zonificacion.js ───────────────────────────────────────────

def parse_js_data_arrays(js_path: Path) -> dict[str, list]:
    """
    Lee datos_zonificacion.js y extrae cada array `const DATA_KEY = [...]`.
    Devuelve dict {key_lowercase: [items...]}.
    """
    text = js_path.read_text(encoding="utf-8")
    # Pattern: `const DATA_FOO = [...];` con [...] que puede tener corchetes anidados
    # Usamos un parser simple: localiza `const DATA_X = ` y luego encuentra el `];`
    # del nivel exterior contando brackets.
    result = {}
    for match in re.finditer(r"const\s+(DATA_\w+)\s*=\s*\[", text):
        var_name = match.group(1)
        start = match.end() - 1  # posición del `[` exterior
        depth = 0
        end = start
        for i in range(start, len(text)):
            c = text[i]
            if c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        array_str = text[start:end]
        try:
            items = json.loads(array_str)
        except json.JSONDecodeError as e:
            print(f"  ! Failed to parse {var_name}: {e}", file=sys.stderr)
            continue
        key = var_name.replace("DATA_", "").lower()
        result[key] = items
    return result


# ── Geometry helpers ────────────────────────────────────────────────────────

def latlng_to_shapely_polygon(coords_latlng: list) -> Polygon | None:
    """Convierte coords Leaflet [[lat, lon], ...] a Shapely Polygon (lon, lat)."""
    if len(coords_latlng) < 3:
        return None
    try:
        return Polygon([(lon, lat) for lat, lon in coords_latlng])
    except Exception:
        return None


def shapely_polygon_to_latlng(poly: Polygon) -> list:
    """Convierte Shapely Polygon (lon, lat) → Leaflet [[lat, lon], ...]."""
    return [
        [round(lat, COORD_PRECISION), round(lon, COORD_PRECISION)]
        for lon, lat in poly.exterior.coords
    ]


def meters_to_degrees(meters: float, lat: float) -> float:
    """Conversión aproximada metros → grados (latitud aproximada)."""
    return meters / (111_320.0 * math.cos(math.radians(lat)))


def shapely_area_m2(poly: Polygon) -> float:
    """Aproximación del área de un Shapely Polygon (lon, lat) en m²."""
    centroid_lat = poly.centroid.y
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(centroid_lat))
    return poly.area * m_per_deg_lat * m_per_deg_lon


# ── Microsoft Buildings download/parse ──────────────────────────────────────

def download_ms_buildings(cache_path: Path) -> Path:
    """Descarga Minnesota.geojson.zip si no está cacheado."""
    if cache_path.exists():
        size_mb = cache_path.stat().st_size / (1024 * 1024)
        print(f"  Cache hit: {cache_path.name} ({size_mb:.1f} MB)")
        return cache_path

    print(f"  Downloading {MS_BUILDINGS_URL} ...")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(MS_BUILDINGS_URL, stream=True, timeout=120)
    r.raise_for_status()
    total = int(r.headers.get("content-length", 0))
    written = 0
    with open(cache_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=1 << 20):  # 1 MB chunks
            f.write(chunk)
            written += len(chunk)
            if total:
                pct = written / total * 100
                sys.stdout.write(f"\r  Downloaded {written / (1024*1024):.1f} / {total / (1024*1024):.1f} MB ({pct:.0f}%)")
                sys.stdout.flush()
    sys.stdout.write("\n")
    size_mb = cache_path.stat().st_size / (1024 * 1024)
    print(f"  Saved: {cache_path.name} ({size_mb:.1f} MB)")
    return cache_path


def iter_ms_buildings_in_bbox(zip_path: Path, bbox: tuple) -> "Iterator[Polygon]":
    """
    Stream-parse el GeoJSON dentro del zip y yield Polygons en el bbox.
    bbox: (south, west, north, east)
    """
    south, west, north, east = bbox
    print(f"  Streaming MS Buildings, filtering to bbox {bbox}...")

    seen, kept = 0, 0
    with zipfile.ZipFile(zip_path) as zf:
        geojson_files = [n for n in zf.namelist() if n.lower().endswith(".geojson")]
        if not geojson_files:
            raise RuntimeError(f"No .geojson found in {zip_path}")
        name = geojson_files[0]
        print(f"  Reading: {name}")
        with zf.open(name) as f:
            wrapper = io.TextIOWrapper(f, encoding="utf-8")
            for line_no, line in enumerate(wrapper, 1):
                line = line.strip()
                if not line or line.startswith("{") and "FeatureCollection" in line:
                    continue
                if line.endswith(","):
                    line = line[:-1]
                if line in ("]", "}", "]}"):
                    continue
                if not line.startswith("{"):
                    continue
                seen += 1
                try:
                    feature = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if feature.get("type") != "Feature":
                    continue
                geom = feature.get("geometry") or {}
                if geom.get("type") != "Polygon":
                    continue
                coords = geom.get("coordinates", [])
                if not coords:
                    continue
                exterior = coords[0]
                # Quick bbox filter usando primer vértice
                lon0, lat0 = exterior[0]
                if lat0 < south or lat0 > north or lon0 < west or lon0 > east:
                    continue
                # Confirmar centroide en bbox también
                try:
                    poly = shape(geom)
                    c = poly.centroid
                    if not (south <= c.y <= north and west <= c.x <= east):
                        continue
                except Exception:
                    continue
                kept += 1
                yield poly
                if seen % 100_000 == 0:
                    sys.stdout.write(f"\r  Processed {seen:,} features, kept {kept:,}")
                    sys.stdout.flush()

    sys.stdout.write("\n")
    print(f"  Streaming done: {seen:,} features seen, {kept:,} within bbox")


# ── Main pipeline ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Augment OSM data with Microsoft Building Footprints"
    )
    parser.add_argument("--bbox", default=DEFAULT_BBOX,
                        help=f"BBOX 'south,west,north,east' (default: {DEFAULT_BBOX})")
    parser.add_argument("--osm-data", default="../visualizer/datos_zonificacion.js",
                        help="Path to existing OSM datos_zonificacion.js")
    parser.add_argument("--out", default="../visualizer/datos_msbuildings.js",
                        help="Output .js file path")
    parser.add_argument("--cache", default="../.cache/ms-buildings-mn.zip",
                        help="Path to cache Minnesota.geojson.zip")
    args = parser.parse_args()

    bbox = tuple(float(x) for x in args.bbox.split(","))
    osm_js_path = Path(args.osm_data)
    out_path = Path(args.out)
    cache_path = Path(args.cache)

    print("MS Buildings Augmentation Pipeline — Sesión 1.8")
    print(f"BBOX        : {bbox}")
    print(f"OSM source  : {osm_js_path}")
    print(f"Output      : {out_path}")
    print(f"Cache       : {cache_path}")
    print()

    # ── Step 1: Parse existing OSM data ────────────────────────────────────
    print("[1/5] Parsing existing OSM data from datos_zonificacion.js ...")
    if not osm_js_path.exists():
        sys.exit(f"  ERROR: {osm_js_path} no existe. Corre extract_zoning.py primero.")
    osm_data = parse_js_data_arrays(osm_js_path)
    print(f"  Parsed {len(osm_data)} DATA_* arrays")
    for k, v in osm_data.items():
        print(f"    {k:<16}: {len(v):>6} items")

    # ── Step 2: Build STRtree de OSM buildings (para dedup) + landuse (para clasif) ──
    print("\n[2/5] Building spatial indices...")

    # Threshold para separar "block" (landuse polygon grande) de "building" (individual).
    # 3,000 m² coincide con TIER_THRESHOLDS.res_low_house del visualizer (JS).
    # Una casa típica = ~150 m², una manzana = ~50,000 m².
    AREA_THRESHOLD_M2 = 3000.0

    osm_buildings_polys = []   # individuales, para dedup
    osm_buildings_centroids = []  # centroides para STRtree
    landuse_polys = {k: [] for k in LANDUSE_TO_CS2}

    # Mapeo de cs2_key del OSM al landuse type (para reconstruir el "landuse" virtual)
    KEY_TO_LANDUSE = {
        "res_low_house": "residential",
        "res_row":       "residential",
        "res_med":       "residential",
        "res_mixed":     "residential",
        "res_low_rent":  "residential",
        "res_high":      "residential",
        "com_low":       "commercial",
        "com_high":      "commercial",
        "office_low":    "office",
        "office_high":   "office",
        "industrial":    "industrial",
    }

    for key, items in osm_data.items():
        landuse_type = KEY_TO_LANDUSE.get(key)
        for item in items:
            poly = latlng_to_shapely_polygon(item.get("coords", []))
            if poly is None:
                continue
            area_m2 = shapely_area_m2(poly)
            if area_m2 >= AREA_THRESHOLD_M2:
                # Es un block (landuse grande) → usar para clasificación
                if landuse_type:
                    landuse_polys[landuse_type].append(poly)
            else:
                # Es un building individual → usar para dedup
                osm_buildings_centroids.append(poly.centroid)

    print(f"  Landuse blocks por tipo:")
    for k, v in landuse_polys.items():
        print(f"    {k:<12}: {len(v):>5}")
    print(f"  OSM building centroids (dedup): {len(osm_buildings_centroids):,}")

    # STRtrees por tipo (para contención exacta con prioridad)
    landuse_trees = {
        t: (STRtree(polys) if polys else None) for t, polys in landuse_polys.items()
    }
    # STRtree unificado (para "nearest landuse" cuando no hay contención exacta)
    all_landuse_polys = []
    all_landuse_types = []
    for t, polys in landuse_polys.items():
        for p in polys:
            all_landuse_polys.append(p)
            all_landuse_types.append(t)
    all_landuse_tree = STRtree(all_landuse_polys) if all_landuse_polys else None
    osm_centroids_tree = STRtree(osm_buildings_centroids) if osm_buildings_centroids else None

    # Prioridad para contención exacta (la más específica gana cuando solapan)
    LANDUSE_PRIORITY = ["industrial", "office", "commercial", "retail", "residential"]

    # Fallback config: si no hay contención exacta, usar nearest landuse dentro de 500m.
    # Si tampoco, asumir res_low_house (most common type para edificios sin contexto OSM).
    NEAREST_FALLBACK_M = 500.0

    # ── Step 3: Download + stream MS Buildings ────────────────────────────
    print("\n[3/5] Downloading Microsoft Buildings dataset...")
    zip_path = download_ms_buildings(cache_path)

    print("\n[4/5] Processing MS Buildings (dedup + classify)...")

    # Precomputar radio de dedup en grados (lat media del bbox)
    lat_mid = (bbox[0] + bbox[2]) / 2
    dedup_radius_deg = meters_to_degrees(DEDUP_RADIUS_M, lat_mid)

    output = {k: [] for k in set(LANDUSE_TO_CS2.values())}
    output.setdefault("res_low_house", [])  # ensure default key exists
    stats = {
        "ms_total_in_bbox": 0,
        "skipped_dup_with_osm": 0,
        "classified_by_exact_landuse": 0,
        "classified_by_nearest_landuse": 0,
        "classified_by_default_residential": 0,
        "classified": {k: 0 for k in output},
    }

    # MS buildings tienen ID interno por enumeración (no OSM id)
    next_ms_id = 1

    for ms_poly in iter_ms_buildings_in_bbox(zip_path, bbox):
        stats["ms_total_in_bbox"] += 1
        centroid = ms_poly.centroid

        # ── Dedup contra OSM building centroids ──
        if osm_centroids_tree is not None:
            nearby = osm_centroids_tree.query(centroid.buffer(dedup_radius_deg))
            duplicate = False
            for idx in nearby:
                if centroid.distance(osm_buildings_centroids[idx]) <= dedup_radius_deg:
                    duplicate = True
                    break
            if duplicate:
                stats["skipped_dup_with_osm"] += 1
                continue

        # ── Clasificación por landuse ──
        # 1) Exact containment con prioridad (industrial > office > commercial > residential)
        cs2_key = None
        for landuse_type in LANDUSE_PRIORITY:
            tree = landuse_trees.get(landuse_type)
            if tree is None:
                continue
            for idx in tree.query(centroid):
                if landuse_polys[landuse_type][idx].contains(centroid):
                    cs2_key = LANDUSE_TO_CS2[landuse_type]
                    break
            if cs2_key:
                break

        if cs2_key:
            stats["classified_by_exact_landuse"] += 1
        else:
            # 2) Nearest landuse dentro del threshold
            if all_landuse_tree is not None:
                nearest_idx = all_landuse_tree.nearest(centroid)
                nearest_poly = all_landuse_polys[nearest_idx]
                dist_deg = nearest_poly.distance(centroid)
                # Convertir dist en grados → metros aprox a latitud actual
                dist_m = dist_deg * 111_320.0 * math.cos(math.radians(centroid.y))
                if dist_m <= NEAREST_FALLBACK_M:
                    cs2_key = LANDUSE_TO_CS2[all_landuse_types[nearest_idx]]
                    stats["classified_by_nearest_landuse"] += 1

        if cs2_key is None:
            # 3) Default: residencial. Mejor que descartar — la mayoría de buildings
            #    sin landuse OSM son casas en barrios suburbanos.
            cs2_key = "res_low_house"
            stats["classified_by_default_residential"] += 1

        output[cs2_key].append({
            "id": f"ms{next_ms_id}",
            "coords": shapely_polygon_to_latlng(ms_poly),
        })
        next_ms_id += 1
        stats["classified"][cs2_key] += 1

        if stats["ms_total_in_bbox"] % 50_000 == 0:
            sys.stdout.write(f"\r  Procesados {stats['ms_total_in_bbox']:,} buildings MS...")
            sys.stdout.flush()

    sys.stdout.write("\n")

    # ── Step 5: Write output ────────────────────────────────────────────────
    print("\n[5/5] Writing output...")
    print(f"  MS buildings total in bbox          : {stats['ms_total_in_bbox']:,}")
    print(f"  Skipped — duplicado con OSM         : {stats['skipped_dup_with_osm']:,}")
    print(f"  Classified by EXACT landuse contains: {stats['classified_by_exact_landuse']:,}")
    print(f"  Classified by NEAREST landuse <500m : {stats['classified_by_nearest_landuse']:,}")
    print(f"  Classified by DEFAULT residential   : {stats['classified_by_default_residential']:,}")
    print(f"  Clasificados (añadidos por zona):")
    total_classified = 0
    for k, n in stats["classified"].items():
        print(f"    {k:<14}: {n:,}")
        total_classified += n
    print(f"  TOTAL añadido                       : {total_classified:,}")

    # Escribir como módulo JS — un array por cs2_key
    ts = datetime.now(timezone.utc).isoformat()
    lines = [
        f"// Auto-generated by extract_msbuildings.py — {ts}",
        f"// Microsoft USBuildingFootprints augmentation",
        f"// BBOX: {','.join(str(x) for x in bbox)}",
        f"// Total MS buildings added: {total_classified:,}",
        "",
    ]
    for key in sorted(output):
        var = f"DATA_MS_{key.upper()}"
        lines.append(f"const {var} = {json.dumps(output[key], separators=(',', ':'))};")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"\nDone. {out_path} — {size_mb:.1f} MB — {total_classified:,} buildings")


if __name__ == "__main__":
    main()
