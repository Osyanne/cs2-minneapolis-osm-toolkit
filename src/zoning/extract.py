#!/usr/bin/env python3
"""
extract.py — CS2 OSM Toolkit Zoning Pipeline (v3.3, multi-city)
===============================================================
Extrae polígonos de zonificación real desde OpenStreetMap y los exporta
como un archivo JS listo para el visualizador Leaflet.

Cambios v3.0 (vs v2.0):
- Modelo de zonas realineado a CS2 oficial (13 keys total)
- Residencial dividido en 6 sub-tipos: low_house, row, med, mixed, low_rent, high
- Office dividido en low/high
- Retail Hub fusionado en com_low
- mixed + mixed_res_com fusionados en res_mixed
- Heurística de footprint (m²) para distinguir Low Rent vs Med apartments

Uso:
    cd src
    uv run extract-zoning --city minneapolis
    uv run extract-zoning --city manhattan
    uv run extract-zoning --bbox "44.86,-93.38,45.05,-93.17" --slug minneapolis
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from shared.overpass_client import query_with_retry
from shared.registry import load_cities, get_city, CityNotFoundError, RegistryError, save_manifest_entry
from zoning.classifiers import (
    classify_apartment,
    classify_residential_subtype,
    classify_landuse_residential,
    classify_commercial,
    classify_office,
    classify_parking,
    classify_generic_building_by_area,
    is_civic_amenity_tag,
    polygon_area_m2,
    LANDUSE_TO_CS2_KEY,
)
from zoning.zones import CS2_LABELS, build_queries


# ── Geometry helpers ─────────────────────────────────────────────────────────

def coords_from_way(element: dict) -> list | None:
    geom = element.get("geometry", [])
    if len(geom) < 3:
        return None
    return [[pt["lat"], pt["lon"]] for pt in geom]


def coords_from_relation(element: dict) -> list | None:
    members = element.get("members", [])
    outers = [
        m for m in members
        if m.get("role") == "outer"
        and len(m.get("geometry", [])) > 2
    ]
    if not outers:
        return None
    outers.sort(key=lambda m: len(m["geometry"]), reverse=True)
    return [[pt["lat"], pt["lon"]] for pt in outers[0]["geometry"]]


def extract_coords(element: dict) -> list | None:
    if element["type"] == "way":
        return coords_from_way(element)
    return coords_from_relation(element)


def make_item(el: dict, coords: list, cs2_key: str) -> dict:
    tags = el.get("tags") or {}
    return {
        "id": el["id"],
        "name": tags.get("name", ""),
        "coords": coords,
        "cs2_key": cs2_key,
        "cs2": CS2_LABELS[cs2_key],
    }


# ── City resolution ──────────────────────────────────────────────────────────

def resolve_city_args(
    city: str | None,
    bbox: str | None,
    slug: str | None,
    cities_file: Path,
) -> tuple[str, str]:
    """Resuelve los argumentos CLI a (bbox, slug) finales.

    Modos:
    - --city <slug>: lee cities.json, deriva bbox del registro
    - --bbox X --slug Y: escape hatch sin tocar registro
    - Ambos --city y --bbox: --city gana (con warning)
    - Solo --bbox: error (necesita --slug)
    - Nada: error
    """
    if city is not None:
        if bbox is not None:
            print(
                f"[WARNING] Se ignoró --bbox '{bbox}' porque --city='{city}' tiene prioridad.",
                file=sys.stderr,
            )
        cities = load_cities(cities_file)
        entry = get_city(cities, city)
        s, w, n, e = entry["bbox"]
        return (f"{s},{w},{n},{e}", city)
    if bbox is not None:
        if slug is None:
            raise ValueError(
                "Si pasas --bbox debes pasar también --slug "
                "(usado para el output path visualizer/cities/<slug>/)"
            )
        return (bbox, slug)
    raise ValueError("Debes pasar --city o --bbox+--slug")


# ── Generic-building spatial join ────────────────────────────────────────────

def _collect_landuse_polygons(raw: dict) -> list:
    """
    Extrae los polígonos landuse=* presentes en los resultados raw de Overpass
    y los pares con su CS2 key. Devuelve [(shapely.Polygon, cs2_key), ...].

    Fuentes consideradas:
      - raw["landuse_residential"]: TODO el contenido es landuse=residential
        (la query es específica).
      - raw["commercial"]: filtrar elementos con landuse ∈ {commercial, retail}.
      - raw["industrial"]: filtrar elementos con landuse=industrial.
      - raw["office"]:     filtrar elementos con landuse=office.
    """
    from shapely.geometry import Polygon as _ShapelyPolygon

    polys: list = []

    def _try_add(el: dict, cs2_key: str) -> None:
        coords = extract_coords(el)
        if not coords or len(coords) < 4:  # cerrado mínimo: 3 puntos + repetición
            return
        try:
            # shapely usa (x=lon, y=lat); coords es [[lat, lon], ...]
            shp = _ShapelyPolygon([(c[1], c[0]) for c in coords])
        except Exception:
            return
        if not shp.is_valid or shp.is_empty:
            return
        polys.append((shp, cs2_key))

    for el in raw.get("landuse_residential", []):
        _try_add(el, "res_low_house")

    for el in raw.get("commercial", []):
        landuse = ((el.get("tags") or {}).get("landuse") or "").lower()
        if landuse in ("commercial", "retail"):
            _try_add(el, "com_low")

    for el in raw.get("industrial", []):
        landuse = ((el.get("tags") or {}).get("landuse") or "").lower()
        if landuse == "industrial":
            _try_add(el, "industrial")

    for el in raw.get("office", []):
        landuse = ((el.get("tags") or {}).get("landuse") or "").lower()
        if landuse == "office":
            _try_add(el, "office_low")

    return polys


def _build_amenity_tree(raw: dict):
    """
    Construye STRtree de civic amenity points (nodes) desde raw["civic_amenities"].

    Returns (STRtree | None, list[Point] | None). Both None si no hay amenities.
    """
    from shapely.geometry import Point as _ShapelyPoint
    from shapely.strtree import STRtree

    elements = raw.get("civic_amenities", [])
    points = []
    for el in elements:
        if el.get("type") != "node":
            continue
        lat = el.get("lat")
        lon = el.get("lon")
        if lat is None or lon is None:
            continue
        # shapely: (x=lon, y=lat)
        points.append(_ShapelyPoint(lon, lat))

    if not points:
        return (None, None)
    return (STRtree(points), points)


def _has_civic_amenity_near(
    centroid,
    amenity_tree,
    amenity_points,
    max_dist_m: float = 30.0,
) -> bool:
    """
    True si hay un node civic amenity dentro de max_dist_m del centroide.

    Usa STRtree para query rápido + check de distancia equirectangular en metros.
    """
    if amenity_tree is None or amenity_points is None:
        return False
    # Convertir max_dist_m a degrees al latitude del centroide. Aproximación
    # equirectangular: 1 grado lat ≈ 111320 m; 1 grado lon ≈ 111320 m * cos(lat).
    import math
    lat0 = centroid.y
    cos_lat = math.cos(math.radians(lat0))
    deg_per_m_lat = 1.0 / 111_320.0
    deg_per_m_lon = 1.0 / (111_320.0 * max(cos_lat, 0.01))
    # Buffer del centroide en grados (envelope cuadrado conservador)
    buf_lat = deg_per_m_lat * max_dist_m
    buf_lon = deg_per_m_lon * max_dist_m
    # shapely envelope: usar bounding box query
    bbox = (
        centroid.x - buf_lon, centroid.y - buf_lat,
        centroid.x + buf_lon, centroid.y + buf_lat,
    )
    from shapely.geometry import box
    candidates = amenity_tree.query(box(*bbox))
    for cand in candidates:
        # shapely 2.x: indices; shapely 1.x: geometries
        if hasattr(cand, "__index__"):
            pt = amenity_points[int(cand)]
        else:
            pt = cand
        # Distancia equirectangular en metros
        dx_m = (pt.x - centroid.x) * 111_320.0 * cos_lat
        dy_m = (pt.y - centroid.y) * 111_320.0
        if (dx_m * dx_m + dy_m * dy_m) <= (max_dist_m * max_dist_m):
            return True
    return False


def _process_generic_buildings(
    raw: dict,
    output: dict,
    seen_ids: set,
    add_fn,
) -> tuple[int, int, int, int]:
    """
    Procesa raw["generic_buildings"] (building=yes) y los clasifica vía
    spatial join contra landuse polygons + heurística de área como fallback.
    Después aplica amenity cross-reference: si el building se clasificó por
    área pura Y hay un node civic amenity (school/hospital/church/...) dentro
    de 30m del centroide, se reclasifica a com_low (no industrial).

    Returns:
      (total_added, by_landuse, by_area, by_amenity_override)
    """
    from shapely.geometry import Polygon as _ShapelyPolygon
    from shapely.strtree import STRtree

    elements = raw.get("generic_buildings", [])
    if not elements:
        return (0, 0, 0, 0)

    landuse_polys = _collect_landuse_polygons(raw)
    landuse_geoms = [lp[0] for lp in landuse_polys]
    landuse_keys = [lp[1] for lp in landuse_polys]
    tree = STRtree(landuse_geoms) if landuse_geoms else None

    amenity_tree, amenity_points = _build_amenity_tree(raw)

    added = 0
    by_landuse = 0
    by_area = 0
    by_amenity = 0

    for el in elements:
        if el["id"] in seen_ids:
            continue
        coords = extract_coords(el)
        if not coords:
            continue

        try:
            building_poly = _ShapelyPolygon([(c[1], c[0]) for c in coords])
        except Exception:
            continue
        if not building_poly.is_valid or building_poly.is_empty:
            continue

        cs2_key = None
        method = None
        if tree is not None:
            centroid = building_poly.centroid
            # STRtree.query returns geometries OR indices depending on version;
            # normalizamos a iterable de geometrías candidatas.
            try:
                candidates = tree.query(centroid)
                for cand in candidates:
                    # shapely 2.x: query() devuelve indices (numpy array).
                    if isinstance(cand, (int,)) or hasattr(cand, "__index__"):
                        geom = landuse_geoms[int(cand)]
                        key = landuse_keys[int(cand)]
                    else:
                        # shapely 1.x compat path: returns geometry directly.
                        geom = cand
                        try:
                            key = landuse_keys[landuse_geoms.index(geom)]
                        except ValueError:
                            continue
                    if geom.contains(centroid):
                        cs2_key = key
                        method = "landuse"
                        break
            except Exception:
                cs2_key = None

        if cs2_key is not None:
            by_landuse += 1
        else:
            area = polygon_area_m2(coords)
            cs2_key = classify_generic_building_by_area(area)
            method = "area"
            # Amenity cross-reference (v3.3.7): si hay un civic amenity cerca,
            # promote el building a com_low (no es industrial/residencial puro,
            # es civic). Solo aplica si la clasificación fue por área pura.
            if _has_civic_amenity_near(
                building_poly.centroid, amenity_tree, amenity_points, max_dist_m=30.0
            ):
                cs2_key = "com_low"
                method = "amenity"
                by_amenity += 1
            else:
                by_area += 1

        if add_fn(el, cs2_key):
            # Inject method field on the item we just appended. Items added by
            # tag-based classifiers (apartments, residential_subtypes, etc.) do
            # NOT get a method field — implicitly treated as "tag" (highest
            # confidence) by the visualizer.
            output[cs2_key][-1]["method"] = method
            added += 1

    return (added, by_landuse, by_area, by_amenity)


# ── CLI parsing ──────────────────────────────────────────────────────────────

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI args for extract-zoning.

    Args:
        argv: Optional list of args (for testing). If None, uses sys.argv.

    Returns:
        argparse.Namespace with attributes: city, bbox, slug, source,
        refresh_pbf, cities_file, visualizer_root.
    """
    parser = argparse.ArgumentParser(
        description="Extract OSM zoning data → visualizer prebuilt JS"
    )
    parser.add_argument("--city", help="Slug de cities.json (ej. minneapolis, manhattan)")
    parser.add_argument("--bbox", help="Escape hatch: bbox 's,w,n,e' (requiere --slug)")
    parser.add_argument("--slug", help="Output slug cuando se usa --bbox sin --city")
    parser.add_argument(
        "--cities-file",
        default=None,
        help="Path a cities.json (default: <repo_root>/cities.json)",
    )
    parser.add_argument(
        "--visualizer-root",
        default=None,
        help="Path a visualizer/ (default: <repo_root>/visualizer)",
    )
    parser.add_argument(
        "--source",
        choices=["pbf", "overpass"],
        default="pbf",
        help="extraction source: 'pbf' (default, local Geofabrik) or 'overpass' (legacy)",
    )
    parser.add_argument(
        "--refresh-pbf",
        action="store_true",
        help="force re-download of regional PBF even if cached (no-op with --source overpass)",
    )
    return parser.parse_args(argv)


# ── Main pipeline ─────────────────────────────────────────────────────────────

def main():
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
    out_path = out_dir / "datos_zonificacion.js"

    print(f"CS2 OSM Toolkit — Zoning Extractor")
    print(f"City         : {slug}")
    print(f"Bounding Box : {bbox}")
    print(f"Source       : {args.source}")
    print(f"Output       : {out_path}\n")

    # ── Step 1: Download all source categories ────────────────────────────────
    # ORDEN IMPORTANTE: mixed_apartments PRIMERO → captura apartments que tienen
    # POIs comerciales dentro (spatial join) → se clasifican como res_mixed.
    # Luego apartments procesa el resto sin spatial join.
    # generic_buildings AL FINAL → solo recoge building=yes que NO fueron
    # capturados por queries específicas (dedup global por OSM id).
    SOURCE_KEYS = [
        "mixed_apartments",
        "apartments",
        "landuse_residential",
        "residential_subtypes",
        "commercial",
        "office",
        "industrial",
        "parking",
        "generic_buildings",
        "civic_amenities",
    ]

    raw: dict[str, list] = {}
    if args.source == "pbf":
        from shared.pbf_cache import ensure_pbf
        from shared.pbf_client import query_batch
        from zoning.zones import build_pbf_filters

        cities = load_cities(cities_file)
        city_entry = get_city(cities, slug)
        pbf_region = city_entry.get("pbf_region")
        if not pbf_region:
            raise SystemExit(
                f"[ERROR] City '{slug}' has no 'pbf_region' in cities.json. "
                "Either add it or run with --source overpass."
            )
        pbf_path = ensure_pbf(pbf_region, force_refresh=args.refresh_pbf)

        bbox_tuple = tuple(float(v) for v in bbox.split(","))
        filter_specs = build_pbf_filters(bbox_tuple)

        print(f"[1/2] Extracting {len(SOURCE_KEYS)} source categories from PBF...")
        batch_result = query_batch(pbf_path, bbox_tuple, filter_specs, label="zoning")
        raw = {key: batch_result[key]["elements"] for key in SOURCE_KEYS}
        for key in SOURCE_KEYS:
            print(f"      {key:<24}: {len(raw[key])} elements")
    else:
        queries = build_queries(bbox)
        print(f"[1/2] Downloading {len(SOURCE_KEYS)} source queries from Overpass...")
        for key in SOURCE_KEYS:
            result = query_with_retry(queries[key], key)
            raw[key] = result.get("elements", [])
            print(f"      {key:<24}: {len(raw[key])} elements")

    # ── Step 2: Classify ──────────────────────────────────────────────────────
    print("\n[2/2] Classifying zones into CS2 model...")

    # Output bucketed by CS2 key for the visualizer
    output: dict[str, list] = defaultdict(list)
    skipped = 0
    seen_ids: set[int] = set()

    def add(el: dict, cs2_key: str) -> bool:
        """Add element to output bucket, dedup by OSM id across categories."""
        nonlocal skipped
        if el["id"] in seen_ids:
            return False
        coords = extract_coords(el)
        if not coords:
            skipped += 1
            return False
        seen_ids.add(el["id"])
        output[cs2_key].append(make_item(el, coords, cs2_key))
        return True

    # 0. Mixed apartments — spatial join: apartments con POIs comerciales dentro
    #    Todos los elementos retornados por esta query son Mixed Housing directos.
    for el in raw["mixed_apartments"]:
        add(el, "res_mixed")

    # 1. Apartments — el resto (sin POIs comerciales dentro)
    for el in raw["apartments"]:
        coords = extract_coords(el)
        if not coords:
            continue
        area = polygon_area_m2(coords)
        suffix = classify_apartment(el.get("tags") or {}, area)
        add(el, f"res_{suffix}")

    # 2. Residential subtypes (terrace, townhouse, house, detached, etc.)
    for el in raw["residential_subtypes"]:
        suffix = classify_residential_subtype(el.get("tags") or {})
        if suffix is None:
            continue
        add(el, f"res_{suffix}")

    # 3. Landuse=residential (fallback for areas without specific buildings)
    for el in raw["landuse_residential"]:
        suffix = classify_landuse_residential(el.get("tags") or {})
        add(el, f"res_{suffix}")

    # 4. Commercial
    for el in raw["commercial"]:
        coords = extract_coords(el)
        if not coords:
            continue
        area = polygon_area_m2(coords)
        suffix = classify_commercial(el.get("tags") or {}, area)
        add(el, f"com_{suffix}")

    # 5. Office (dedup against commercial via seen_ids)
    for el in raw["office"]:
        suffix = classify_office(el.get("tags") or {})
        add(el, f"office_{suffix}")

    # 6. Industrial
    for el in raw["industrial"]:
        add(el, "industrial")

    # 7. Parking
    for el in raw["parking"]:
        suffix = classify_parking(el.get("tags") or {})
        add(el, f"prk_{suffix}")

    # 8. Generic buildings (building=yes) — spatial join contra landuse + area heuristic
    #    + amenity cross-reference (v3.3.7).
    #    Cobertura sparse de OSM (small-town LATAM/África/Asia) suele tener la mayoría
    #    de los edificios mapeados como building=yes sin clasificación. Esta pasada los
    #    recoge: si caen dentro de un polígono landuse=* conocido, se clasifican por
    #    él; si no, heurística por área. Tras eso, si el building está cerca (≤30m) de
    #    una amenity civic (school/hospital/church/etc.) Y se clasificó por área pura,
    #    se reclasifica a com_low (no industrial) para reducir falsos positivos típicos.
    (
        generic_added, generic_by_landuse, generic_by_area, generic_by_amenity
    ) = _process_generic_buildings(
        raw, output, seen_ids, add
    )

    # ── Summary ───────────────────────────────────────────────────────────────
    total = sum(len(v) for v in output.values())
    print()
    for key in CS2_LABELS:
        print(f"  {key:<16}: {len(output[key]):>6}  ({CS2_LABELS[key]})")
    print(f"  {'skipped':<16}: {skipped:>6}")
    print(
        f"  {'generic+':<16}: {generic_added:>6}  "
        f"(landuse: {generic_by_landuse}, area: {generic_by_area}, "
        f"amenity-override: {generic_by_amenity})"
    )
    print(f"  {'TOTAL':<16}: {total:>6}")

    # ── Write output ──────────────────────────────────────────────────────────
    ts = datetime.now(timezone.utc).isoformat()
    lines = [
        f"// Auto-generated by extract_zoning.py v3.0 — {ts}",
        f"// {slug} — Zoning — bbox: {bbox}",
        f"// CS2-aligned model: 13 zones (6 res + 2 com + 2 office + 1 ind + 2 prk)",
        f"// Total polygons: {total}",
        "",
    ]
    for key in CS2_LABELS:
        var = f"DATA_{key.upper()}"
        lines.append(f"const {var} = {json.dumps(output[key])};")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"\nDone. {out_path} — {size_mb:.1f} MB — {total} polygons")

    save_manifest_entry(
        visualizer_root=vis_root,
        slug=slug,
        module="zoning",
        file_path=out_path,
        features=total,
    )
    print(f"Manifest      : {vis_root / 'cities' / slug / 'manifest.json'}")


if __name__ == "__main__":
    main()
