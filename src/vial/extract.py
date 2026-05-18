#!/usr/bin/env python3
"""
extract.py — CS2 OSM Toolkit Vial Pipeline (v3.3, multi-city)
=============================================================
Extrae la red vial real desde OpenStreetMap y la exporta como un archivo JS
listo para el visualizador Leaflet (overlay encima del mapa de zonificación).

Salida (`visualizer/cities/<slug>/datos_vial.js`):
    const DATA_VIAL = {
      "highway":    [{ id, name, coords: [[lat,lon],...], cs2_key, cs2 }, ...],
      "major":      [...],
      "minor":      [...],
      "local":      [...],
      "pedestrian": [...],
      "bike":       [...],
    };
    const DATA_VIAL_META = { bbox, generated_at, total_features };

Uso:
    cd src
    uv run extract-vial --city minneapolis
    uv run extract-vial --city manhattan
    uv run extract-vial --bbox "44.86,-93.38,45.05,-93.17" --slug minneapolis
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from shared.overpass_client import query_with_retry
from shared.registry import load_cities, get_city, CityNotFoundError, RegistryError, save_manifest_entry
from vial.classifiers import classify_highway
from vial.zones import VIAL_LABELS, build_vial_query


# ── Geometry helpers ─────────────────────────────────────────────────────────

def linestring_from_way(element: dict) -> list | None:
    """
    Extraer la geometría LineString de un elemento Overpass `way`.

    Devuelve [[lat, lon], ...] con ≥2 puntos, o None si la way es degenerada
    (sin geometry, con <2 puntos, o sin tag highway).
    """
    geom = element.get("geometry") or []
    if len(geom) < 2:
        return None
    return [[pt["lat"], pt["lon"]] for pt in geom]


# ── Output assembly ──────────────────────────────────────────────────────────

def make_feature(el: dict, coords: list, cs2_key: str) -> dict:
    tags = el.get("tags") or {}
    return {
        "id": el["id"],
        "name": tags.get("name", "") or tags.get("ref", ""),
        "coords": coords,
        "cs2_key": cs2_key,
        "cs2": VIAL_LABELS[cs2_key],
        # bridge=yes se preserva como flag para que el visualizer pueda
        # darle un weight +0.5 si lo desea
        "bridge": tags.get("bridge") == "yes",
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
    - Ambos --city y --bbox: --city gana (con warning a stderr)
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


# ── Main pipeline ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Extract OSM road network → JS prebuilt")
    parser.add_argument("--city", help="Slug de cities.json (ej. minneapolis, manhattan)")
    parser.add_argument("--bbox", help="Escape hatch: bbox 's,w,n,e' (requiere --slug)")
    parser.add_argument("--slug", help="Output slug cuando se usa --bbox sin --city")
    parser.add_argument("--cities-file", default=None, help="Path a cities.json (default: <repo_root>/cities.json)")
    parser.add_argument("--visualizer-root", default=None, help="Path a visualizer/ (default: <repo_root>/visualizer)")
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
    out_path = out_dir / "datos_vial.js"

    query = build_vial_query(bbox)

    print(f"CS2 OSM Toolkit — Vial Extractor")
    print(f"City         : {slug}")
    print(f"Bounding Box : {bbox}")
    print(f"Output       : {out_path}\n")

    # ── Step 1: Download highway ways ────────────────────────────────────────
    print("[1/2] Downloading highway ways from Overpass...")
    result = query_with_retry(query, "vial")
    elements = result.get("elements", [])
    print(f"      raw ways: {len(elements)}")

    # ── Step 2: Classify & bucket ────────────────────────────────────────────
    print("\n[2/2] Classifying ways into CS2 categories...")
    buckets: dict[str, list] = defaultdict(list)
    skipped_geom = 0
    skipped_class = 0

    for el in elements:
        coords = linestring_from_way(el)
        if coords is None:
            skipped_geom += 1
            continue
        cs2_key = classify_highway(el.get("tags") or {})
        if cs2_key is None:
            skipped_class += 1
            continue
        buckets[cs2_key].append(make_feature(el, coords, cs2_key))

    total = sum(len(v) for v in buckets.values())

    # ── Summary ──────────────────────────────────────────────────────────────
    print()
    print(f"  {'category':<14}  count")
    print(f"  {'-'*14}  {'-'*6}")
    for key in VIAL_LABELS:
        n = len(buckets.get(key, []))
        print(f"  {key:<14}  {n:>6}")
    print(f"  {'-'*14}  {'-'*6}")
    print(f"  {'TOTAL':<14}  {total:>6}")
    print(f"\n  skipped (no geometry):   {skipped_geom}")
    print(f"  skipped (no classifier): {skipped_class}")

    # ── Write output ─────────────────────────────────────────────────────────
    ts = datetime.now(timezone.utc).isoformat()
    meta = {
        "bbox": bbox,
        "generated_at": ts,
        "total_features": total,
    }
    with out_path.open("w", encoding="utf-8") as f:
        f.write(f"// Auto-generated by extract.py (vial) v3.3 — {ts}\n")
        f.write(f"// {slug} — Vial — bbox: {bbox}\n")
        f.write(f"// Total features: {total}\n\n")
        # Un bucket por categoría
        f.write("const DATA_VIAL = ")
        json.dump(dict(buckets), f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n\n")
        f.write("const DATA_VIAL_META = ")
        json.dump(meta, f, ensure_ascii=False)
        f.write(";\n")

    size_kb = out_path.stat().st_size / 1024
    print(f"\nDone. {out_path} — {size_kb:.1f} KB — {total} features")

    save_manifest_entry(
        visualizer_root=vis_root,
        slug=slug,
        module="vial",
        file_path=out_path,
        features=total,
    )
    print(f"Manifest      : {vis_root / 'cities' / slug / 'manifest.json'}")


if __name__ == "__main__":
    main()
