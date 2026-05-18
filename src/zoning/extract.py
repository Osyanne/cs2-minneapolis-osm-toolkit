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
    polygon_area_m2,
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


# ── Main pipeline ─────────────────────────────────────────────────────────────

def main():
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
    args = parser.parse_args()

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

    queries = build_queries(bbox)

    print(f"CS2 OSM Toolkit — Zoning Extractor")
    print(f"City         : {slug}")
    print(f"Bounding Box : {bbox}")
    print(f"Output       : {out_path}\n")

    # ── Step 1: Download all source categories ────────────────────────────────
    # ORDEN IMPORTANTE: mixed_apartments PRIMERO → captura apartments que tienen
    # POIs comerciales dentro (spatial join) → se clasifican como res_mixed.
    # Luego apartments procesa el resto sin spatial join.
    SOURCE_KEYS = [
        "mixed_apartments",
        "apartments",
        "landuse_residential",
        "residential_subtypes",
        "commercial",
        "office",
        "industrial",
        "parking",
    ]
    print(f"[1/2] Downloading {len(SOURCE_KEYS)} source queries from Overpass...")
    raw: dict[str, list] = {}
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

    # ── Summary ───────────────────────────────────────────────────────────────
    total = sum(len(v) for v in output.values())
    print()
    for key in CS2_LABELS:
        print(f"  {key:<16}: {len(output[key]):>6}  ({CS2_LABELS[key]})")
    print(f"  {'skipped':<16}: {skipped:>6}")
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
