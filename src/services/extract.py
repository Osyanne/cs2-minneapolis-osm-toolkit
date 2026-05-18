#!/usr/bin/env python3
"""
extract.py — CS2 OSM Toolkit Services Pipeline (v3.3, multi-city)
=================================================================
Extrae los servicios públicos reales desde OpenStreetMap y los exporta como
un archivo JS listo para el visualizador Leaflet (overlay encima de los mapas
de zonificación y vial existentes).

Salida (`visualizer/cities/<slug>/datos_servicios.js`):
    const DATA_SERVICES_POLYGONS = {
      health:    [{ id, name, subtype, coords, tags }, ...],
      education: [...], fire: [...], admin: [...], parks: [...],
    };
    const DATA_SERVICES_POINTS = {
      health:    [{ id, name, subtype, coord, tags }, ...],
      education: [...], fire: [...], admin: [...], parks: [...],
    };
    const DATA_SERVICES_META = { bbox, generated_at, total_features };

Uso:
    cd src
    uv run extract-services --city minneapolis
    uv run extract-services --city manhattan
    uv run extract-services --bbox "44.86,-93.38,45.05,-93.17" --slug minneapolis
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from shared.overpass_client import query_with_retry
from shared.registry import load_cities, get_city, CityNotFoundError, RegistryError, save_manifest_entry
from services.classifiers import classify_service, infer_geometry_kind
from services.zones import SERVICES_LABELS, build_services_query


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


# ── Feature assembly ─────────────────────────────────────────────────────────

def make_feature(element: dict, cat: str, kind: str) -> dict:
    """
    Construye el dict de feature para el output JS.

    Para kind='polygon': incluye 'coords' como lista de [lat, lon].
    Para kind='point': incluye 'coord' como [lat, lon] (centroide o primer nodo).
    """
    tags = element.get("tags") or {}
    subtype = (tags.get("amenity") or tags.get("leisure") or tags.get("landuse")
               or tags.get("office") or tags.get("tourism") or "")

    feat = {
        "id": element["id"],
        "name": tags.get("name", ""),
        "subtype": subtype,
        "tags": dict(tags),
    }

    if kind == "polygon":
        geom = element.get("geometry") or []
        feat["coords"] = [[pt["lat"], pt["lon"]] for pt in geom]
    else:  # point
        if element["type"] == "node":
            feat["coord"] = [element["lat"], element["lon"]]
        else:
            # way clasificado como point (geometría corta o no cerrada) —
            # usar primer nodo como anchor
            geom = element.get("geometry") or []
            if geom:
                feat["coord"] = [geom[0]["lat"], geom[0]["lon"]]
            else:
                feat["coord"] = [0.0, 0.0]  # fallback defensivo

    return feat


# ── Pipeline ─────────────────────────────────────────────────────────────────

def run(bbox: str, out_path: Path, slug: str = "unknown") -> dict:
    """
    Ejecuta el pipeline completo: query → classify → split → write.

    Devuelve dict de meta para tests/logging.
    """
    query = build_services_query(bbox)

    # Buckets: cat → {polygon: [...], point: [...]}
    polygons: dict[str, list] = defaultdict(list)
    points: dict[str, list] = defaultdict(list)
    skipped_class = 0

    result = query_with_retry(query, "services")
    elements = result.get("elements", [])

    for el in elements:
        tags = el.get("tags") or {}
        cat = classify_service(tags, el["type"])
        if cat is None:
            skipped_class += 1
            continue
        kind = infer_geometry_kind(el)
        feat = make_feature(el, cat, kind)
        if kind == "polygon":
            polygons[cat].append(feat)
        else:
            points[cat].append(feat)

    # Asegurar las 5 claves siempre presentes
    for key in SERVICES_LABELS:
        polygons.setdefault(key, [])
        points.setdefault(key, [])

    total = sum(len(v) for v in polygons.values()) + sum(len(v) for v in points.values())

    meta = {
        "bbox": bbox,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_features": total,
    }

    # ── Write output ─────────────────────────────────────────────────────────
    with out_path.open("w", encoding="utf-8") as f:
        f.write(f"// Auto-generated by extract.py (services) v3.3 — {meta['generated_at']}\n")
        f.write(f"// {slug} — Services — bbox: {bbox}\n")
        f.write(f"// Total features: {total}\n\n")
        f.write("const DATA_SERVICES_POLYGONS = ")
        json.dump(dict(polygons), f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n\n")
        f.write("const DATA_SERVICES_POINTS = ")
        json.dump(dict(points), f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n\n")
        f.write("const DATA_SERVICES_META = ")
        json.dump(meta, f, ensure_ascii=False)
        f.write(";\n")

    return {
        "polygons": polygons,
        "points": points,
        "meta": meta,
        "total": total,
        "skipped_class": skipped_class,
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Extract OSM public services → JS prebuilt")
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
    out_path = out_dir / "datos_servicios.js"

    print(f"CS2 OSM Toolkit — Services Extractor")
    print(f"City         : {slug}")
    print(f"Bounding Box : {bbox}")
    print(f"Output       : {out_path}")

    summary = run(bbox=bbox, out_path=out_path, slug=slug)

    print("\n[2/2] Splitting features into 5 CS2 buckets...")
    print()
    print(f"  {'category':<12}  polygons  points")
    print(f"  {'-'*12}  {'-'*8}  {'-'*6}")
    for key in SERVICES_LABELS:
        p = len(summary["polygons"].get(key, []))
        n = len(summary["points"].get(key, []))
        print(f"  {key:<12}  {p:>8}  {n:>6}")
    print(f"  {'-'*12}  {'-'*8}  {'-'*6}")
    total = summary["total"]
    print(f"  {'TOTAL':<12}  {total:>17}")
    print(f"\n  skipped (no classifier): {summary['skipped_class']}")
    print(f"\n[OK] Wrote {out_path} ({out_path.stat().st_size / 1024:.1f} KB)")

    save_manifest_entry(
        visualizer_root=vis_root,
        slug=slug,
        module="services",
        file_path=out_path,
        features=summary["total"],
    )
    print(f"Manifest     : {vis_root / 'cities' / slug / 'manifest.json'}")


if __name__ == "__main__":
    main()
