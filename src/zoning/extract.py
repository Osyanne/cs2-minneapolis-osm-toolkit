#!/usr/bin/env python3
"""
extract_zoning.py — CS2 Minneapolis Zoning Pipeline v3.0 (Sesión 1.6)
======================================================================
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
    uv run extract_zoning.py
    uv run extract_zoning.py --bbox "44.86,-93.38,45.05,-93.17"
    uv run extract_zoning.py --out ../visualizer/datos_zonificacion.js
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from overpass_client import query_with_retry
from classifiers import (
    classify_apartment,
    classify_residential_subtype,
    classify_landuse_residential,
    classify_commercial,
    classify_office,
    classify_parking,
    polygon_area_m2,
)
from cs2_zones import CS2_LABELS, MINNEAPOLIS_BBOX, build_queries


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


# ── Main pipeline ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Extract OSM zoning data for CS2 (v3.0)")
    parser.add_argument(
        "--bbox",
        default=MINNEAPOLIS_BBOX,
        help=f"Bounding box 'south,west,north,east' (default: {MINNEAPOLIS_BBOX})"
    )
    parser.add_argument(
        "--out",
        default="../visualizer/datos_zonificacion.js",
        help="Output .js file path"
    )
    args = parser.parse_args()

    bbox = args.bbox
    out_path = Path(args.out)
    queries = build_queries(bbox)

    print("CS2 Minneapolis Zoning Extractor v3.0 — CS2-aligned model")
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
        f"// Minneapolis Zoning — bbox: {bbox}",
        f"// CS2-aligned model: 13 zones (6 res + 2 com + 2 office + 1 ind + 2 prk)",
        f"// Total polygons: {total}",
        "",
    ]
    for key in CS2_LABELS:
        var = f"DATA_{key.upper()}"
        lines.append(f"const {var} = {json.dumps(output[key])};")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"\nDone. {out_path} — {size_mb:.1f} MB — {total} polygons")


if __name__ == "__main__":
    main()
