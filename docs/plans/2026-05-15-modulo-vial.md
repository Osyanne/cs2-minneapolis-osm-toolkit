# Sesión 2 — Módulo Red Vial — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extraer la red vial de Minneapolis desde OpenStreetMap, clasificarla en los 6 tipos de carretera de Cities: Skylines 2 y renderizarla como overlay encima del visualizador de zonificación existente.

**Architecture:** Mismo patrón que el módulo zonificación (Sesiones 1-1.7): un módulo Python (`vial_zones.py` + `vial_classifiers.py` + `extract_vial.py`) que produce un único `datos_vial.js` prebuilt, cargado por el `visualizer/index.html` ya existente como capas LineString superpuestas al mapa de polígonos. Layer Control y leyenda se extienden con una sección **"Vías"** debajo de la sección zonificación. Sin visualizer separado.

**Tech Stack:** Python 3.11 + uv | Overpass API (multi-endpoint con `overpass_client.query_with_retry`) | Leaflet.js Canvas renderer (`L.polyline`) | CartoDB Dark Matter | pytest

**Fecha:** 2026-05-15
**Predecesor:** [Sesión 1.6 — Realineamiento CS2](./2026-05-13-cs2-zone-realignment.md)

---

## Modelo de tipos viales

6 categorías mapeadas 1:1 desde el tag `highway=*` de OSM.

| Clave | Tipo CS2 | Tags OSM | Color fill | Color neon | Weight px |
|---|---|---|---|---|---|
| `highway` | Highway | `motorway`, `motorway_link`, `trunk`, `trunk_link` | `#EF5350` | `#FF8A80` | 3.5 |
| `major` | Major Road | `primary`, `primary_link`, `secondary`, `secondary_link` | `#FFB74D` | `#FFCC80` | 2.5 |
| `minor` | Minor Road | `tertiary`, `tertiary_link`, `residential`, `unclassified` | `#BCAAA4` | `#D7CCC8` | 1.4 |
| `local` | Local Street | `living_street`, `service` | `#78909C` | `#B0BEC5` | 0.8 |
| `pedestrian` | Pedestrian | `pedestrian`, `footway`, `path`, `steps` | `#26C6DA` | `#4DD0E1` | 0.6 |
| `bike` | Bike Lane | `cycleway` | `#66BB6A` | `#81C784` | 0.9 |

**Decisiones:**
- `*_link` rampas se agrupan con su highway "padre" — son visualmente parte de la misma red.
- `unclassified` va a `minor` (es el OSM equivalente a "calle local sin clasificar").
- `path` y `steps` van a `pedestrian` aunque OSM los distingue — para CS2 son lo mismo.
- Service roads NO se filtran por longitud — todas se incluyen (alleys, driveways, parking lot internal). Si el resultado es ruidoso visualmente, se puede filtrar en una iteración futura.
- Puentes (`bridge=yes`) NO se separan en una capa propia — se rendean con el color de su highway tag pero con weight +0.5 si tienen `bridge=yes` para que se distingan visualmente.

---

## Estructura de archivos

**Crear:**
- `src/vial_zones.py` — `VIAL_LABELS` dict + `MINNEAPOLIS_BBOX` (reexport) + `build_vial_query(bbox)` (devuelve **una sola** query Overpass QL)
- `src/vial_classifiers.py` — `classify_highway(tags) -> str | None` mapea `tags["highway"]` a una de las 6 claves
- `src/extract_vial.py` — pipeline CLI (ejecutable con `uv run extract_vial.py`)
- `tests/test_vial.py` — tests pytest para builder, classifier y geometría

**Modificar:**
- `visualizer/index.html` — añadir `<script src="datos_vial.js" onerror="window.__noVialPrebuilt=true"></script>`, definir `VIAL_TYPES`, `vialGroups`, función `renderVialFeatures()`, integrar al Layer Control y a la leyenda
- `pyproject.toml` en `src/` — añadir script entry-point `extract_vial = "extract_vial:main"`

**No tocar:**
- `src/cs2_zones.py`, `src/classifiers.py`, `src/extract_zoning.py`, `src/overpass_client.py` — el módulo zonificación queda intacto.

---

## Tareas

### Tarea 1: Marcar el plan en disco

**Files:**
- Create: `docs/plans/2026-05-15-modulo-vial.md` (este archivo)

- [ ] **Step 1: Confirmar que el plan existe en disco**

Run: `ls docs/plans/2026-05-15-modulo-vial.md`
Expected: el archivo existe.

- [ ] **Step 2: Commit**

```bash
git add docs/plans/2026-05-15-modulo-vial.md
git commit -m "docs(vial): plan formal Sesión 2 — Módulo Red Vial"
```

---

### Tarea 2: `src/vial_zones.py` — labels + query builder

**Files:**
- Create: `src/vial_zones.py`
- Test: `tests/test_vial.py`

- [ ] **Step 1: Crear test fallido `tests/test_vial.py`**

Crear el archivo con el siguiente contenido:

```python
"""Tests del módulo vial (Sesión 2)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


BBOX = "44.86,-93.38,45.05,-93.17"

# Las 6 categorías viales CS2
EXPECTED_VIAL_KEYS = {"highway", "major", "minor", "local", "pedestrian", "bike"}


def test_vial_labels_has_six_keys():
    from vial_zones import VIAL_LABELS
    assert set(VIAL_LABELS.keys()) == EXPECTED_VIAL_KEYS


def test_vial_labels_are_human_readable():
    from vial_zones import VIAL_LABELS
    assert VIAL_LABELS["highway"] == "Highway"
    assert VIAL_LABELS["major"] == "Major Road"
    assert VIAL_LABELS["minor"] == "Minor Road"
    assert VIAL_LABELS["local"] == "Local Street"
    assert VIAL_LABELS["pedestrian"] == "Pedestrian Path"
    assert VIAL_LABELS["bike"] == "Bike Lane"


def test_build_vial_query_contains_bbox_and_all_highway_tags():
    from vial_zones import build_vial_query
    q = build_vial_query(BBOX)
    # El bbox debe estar embebido
    assert BBOX in q
    # Todas las categorías highway deben aparecer en la regex
    for tag in [
        "motorway", "trunk", "primary", "secondary", "tertiary",
        "residential", "unclassified", "living_street", "service",
        "pedestrian", "footway", "path", "steps", "cycleway",
    ]:
        assert tag in q, f"falta '{tag}' en query"
    # Debe ser una sola query con out body geom
    assert "out body geom" in q
    assert "[out:json]" in q
```

- [ ] **Step 2: Correr test para verificar que falla**

Run: `cd src && uv run pytest ../tests/test_vial.py -v`
Expected: 3 FAILED con `ModuleNotFoundError: No module named 'vial_zones'`

- [ ] **Step 3: Implementar `src/vial_zones.py`**

```python
"""
vial_zones.py — Modelo de red vial CS2 (Sesión 2, 2026-05-15)
==============================================================
6 categorías de carretera alineadas a Cities: Skylines 2:

  highway     → motorway / trunk (+ _link)        — autopistas
  major       → primary / secondary (+ _link)     — vías principales
  minor       → tertiary / residential / unclas.  — calles menores
  local       → living_street / service           — calles locales
  pedestrian  → pedestrian / footway / path/steps — peatonal
  bike        → cycleway                          — ciclovías

Diseño de query:
  - UNA sola query Overpass cubre las 6 categorías usando regex sobre highway=*
  - out body geom: cada way trae su geometría LineString completa en una pasada
  - timeout 180s (Minneapolis tiene ~50k ways highway en este bbox)
"""

VIAL_LABELS = {
    "highway":    "Highway",
    "major":      "Major Road",
    "minor":      "Minor Road",
    "local":      "Local Street",
    "pedestrian": "Pedestrian Path",
    "bike":       "Bike Lane",
}

# Reexport para no duplicar — los pipelines viales y de zonificación comparten bbox
MINNEAPOLIS_BBOX = "44.86,-93.38,45.05,-93.17"


def build_vial_query(bbox: str) -> str:
    """
    Construir una query Overpass QL que devuelve todos los ways con tag
    highway en {motorway, trunk, primary, secondary, tertiary, residential,
    unclassified, living_street, service, pedestrian, footway, path, steps,
    cycleway} (incluyendo variantes _link para las 4 primeras), con geometría.
    """
    highway_regex = (
        "motorway|motorway_link|trunk|trunk_link|"
        "primary|primary_link|secondary|secondary_link|"
        "tertiary|tertiary_link|residential|unclassified|"
        "living_street|service|"
        "pedestrian|footway|path|steps|"
        "cycleway"
    )
    return f"""
[out:json][timeout:180];
(
  way["highway"~"^({highway_regex})$"]({bbox});
);
out body geom;
""".strip()
```

- [ ] **Step 4: Correr test para verificar que pasa**

Run: `cd src && uv run pytest ../tests/test_vial.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/vial_zones.py tests/test_vial.py
git commit -m "feat(vial): modelo de 6 categorías viales + query Overpass"
```

---

### Tarea 3: `src/vial_classifiers.py` — mapeo highway → categoría CS2

**Files:**
- Create: `src/vial_classifiers.py`
- Modify: `tests/test_vial.py` (añadir tests al final)

- [ ] **Step 1: Añadir tests fallidos a `tests/test_vial.py`**

Append al final del archivo:

```python


# ── classifier tests ─────────────────────────────────────────────────────────

def test_classify_highway_motorway_and_link():
    from vial_classifiers import classify_highway
    assert classify_highway({"highway": "motorway"}) == "highway"
    assert classify_highway({"highway": "motorway_link"}) == "highway"
    assert classify_highway({"highway": "trunk"}) == "highway"
    assert classify_highway({"highway": "trunk_link"}) == "highway"


def test_classify_highway_major():
    from vial_classifiers import classify_highway
    assert classify_highway({"highway": "primary"}) == "major"
    assert classify_highway({"highway": "primary_link"}) == "major"
    assert classify_highway({"highway": "secondary"}) == "major"
    assert classify_highway({"highway": "secondary_link"}) == "major"


def test_classify_highway_minor():
    from vial_classifiers import classify_highway
    assert classify_highway({"highway": "tertiary"}) == "minor"
    assert classify_highway({"highway": "tertiary_link"}) == "minor"
    assert classify_highway({"highway": "residential"}) == "minor"
    assert classify_highway({"highway": "unclassified"}) == "minor"


def test_classify_highway_local():
    from vial_classifiers import classify_highway
    assert classify_highway({"highway": "living_street"}) == "local"
    assert classify_highway({"highway": "service"}) == "local"


def test_classify_highway_pedestrian():
    from vial_classifiers import classify_highway
    assert classify_highway({"highway": "pedestrian"}) == "pedestrian"
    assert classify_highway({"highway": "footway"}) == "pedestrian"
    assert classify_highway({"highway": "path"}) == "pedestrian"
    assert classify_highway({"highway": "steps"}) == "pedestrian"


def test_classify_highway_bike():
    from vial_classifiers import classify_highway
    assert classify_highway({"highway": "cycleway"}) == "bike"


def test_classify_highway_unknown_returns_none():
    from vial_classifiers import classify_highway
    assert classify_highway({"highway": "bus_guideway"}) is None
    assert classify_highway({"highway": "raceway"}) is None
    assert classify_highway({}) is None  # sin tag highway
    assert classify_highway({"highway": ""}) is None
```

- [ ] **Step 2: Correr tests para verificar que fallan**

Run: `cd src && uv run pytest ../tests/test_vial.py -v`
Expected: 7 nuevos FAILED con `ModuleNotFoundError: No module named 'vial_classifiers'`

- [ ] **Step 3: Implementar `src/vial_classifiers.py`**

```python
"""
vial_classifiers.py — Clasificador de tags highway → categoría CS2 (Sesión 2)
=============================================================================
Mapeo puro tabla → categoría. Sin heurísticas, sin geometría: el tag
highway=* es suficiente para decidir la categoría CS2.

  motorway, motorway_link, trunk, trunk_link        → highway
  primary, primary_link, secondary, secondary_link  → major
  tertiary, tertiary_link, residential, unclassif.  → minor
  living_street, service                            → local
  pedestrian, footway, path, steps                  → pedestrian
  cycleway                                          → bike
  otros / ausente                                   → None (omitir)
"""

_HIGHWAY_TO_CS2 = {
    # highway
    "motorway":       "highway",
    "motorway_link":  "highway",
    "trunk":          "highway",
    "trunk_link":     "highway",
    # major
    "primary":        "major",
    "primary_link":   "major",
    "secondary":      "major",
    "secondary_link": "major",
    # minor
    "tertiary":       "minor",
    "tertiary_link":  "minor",
    "residential":    "minor",
    "unclassified":   "minor",
    # local
    "living_street":  "local",
    "service":        "local",
    # pedestrian
    "pedestrian":     "pedestrian",
    "footway":        "pedestrian",
    "path":           "pedestrian",
    "steps":          "pedestrian",
    # bike
    "cycleway":       "bike",
}


def classify_highway(tags: dict) -> str | None:
    """
    Devuelve la categoría CS2 ('highway' | 'major' | 'minor' | 'local' |
    'pedestrian' | 'bike') o None si el tag highway falta o no es soportado.
    """
    hw = (tags.get("highway") or "").lower()
    return _HIGHWAY_TO_CS2.get(hw)
```

- [ ] **Step 4: Correr tests para verificar que pasan**

Run: `cd src && uv run pytest ../tests/test_vial.py -v`
Expected: 10 PASSED (3 anteriores + 7 nuevos)

- [ ] **Step 5: Commit**

```bash
git add src/vial_classifiers.py tests/test_vial.py
git commit -m "feat(vial): classifier highway → 6 categorías CS2 + tests"
```

---

### Tarea 4: `src/extract_vial.py` — pipeline CLI

**Files:**
- Create: `src/extract_vial.py`
- Test: `tests/test_vial.py` (añadir test de la helper de geometría)

- [ ] **Step 1: Añadir test fallido de geometría a `tests/test_vial.py`**

Append al final del archivo:

```python


# ── geometry helper tests ────────────────────────────────────────────────────

def test_linestring_from_way_returns_list_of_latlon_pairs():
    from extract_vial import linestring_from_way
    el = {
        "type": "way",
        "id": 1,
        "geometry": [
            {"lat": 44.97, "lon": -93.27},
            {"lat": 44.98, "lon": -93.26},
            {"lat": 44.99, "lon": -93.25},
        ],
        "tags": {"highway": "primary"},
    }
    coords = linestring_from_way(el)
    assert coords == [[44.97, -93.27], [44.98, -93.26], [44.99, -93.25]]


def test_linestring_from_way_skips_degenerate():
    from extract_vial import linestring_from_way
    # Una way con un solo punto no es una línea
    el = {"type": "way", "id": 2, "geometry": [{"lat": 44.97, "lon": -93.27}]}
    assert linestring_from_way(el) is None
    # Sin geometry
    assert linestring_from_way({"type": "way", "id": 3, "geometry": []}) is None
    assert linestring_from_way({"type": "way", "id": 4}) is None
```

- [ ] **Step 2: Correr test para verificar que falla**

Run: `cd src && uv run pytest ../tests/test_vial.py -v`
Expected: 2 nuevos FAILED con `ModuleNotFoundError: No module named 'extract_vial'`

- [ ] **Step 3: Implementar `src/extract_vial.py`**

```python
#!/usr/bin/env python3
"""
extract_vial.py — CS2 Minneapolis Red Vial Pipeline (Sesión 2)
==============================================================
Extrae la red vial real desde OpenStreetMap y la exporta como un archivo JS
listo para el visualizador Leaflet (overlay encima del mapa de zonificación).

Salida (`visualizer/datos_vial.js`):
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
    uv run extract_vial.py
    uv run extract_vial.py --bbox "44.86,-93.38,45.05,-93.17"
    uv run extract_vial.py --out ../visualizer/datos_vial.js
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from overpass_client import query_with_retry
from vial_classifiers import classify_highway
from vial_zones import VIAL_LABELS, MINNEAPOLIS_BBOX, build_vial_query


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


# ── Main pipeline ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Extract OSM road network for CS2 Minneapolis (Sesión 2)"
    )
    parser.add_argument(
        "--bbox",
        default=MINNEAPOLIS_BBOX,
        help=f"Bounding box 'south,west,north,east' (default: {MINNEAPOLIS_BBOX})",
    )
    parser.add_argument(
        "--out",
        default="../visualizer/datos_vial.js",
        help="Output .js file path",
    )
    args = parser.parse_args()

    bbox = args.bbox
    out_path = Path(args.out)
    query = build_vial_query(bbox)

    print("CS2 Minneapolis Vial Extractor — Sesión 2")
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
    meta = {
        "bbox": bbox,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_features": total,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        f.write("// Auto-generated by extract_vial.py — do not edit manually\n")
        f.write(f"// {meta['generated_at']} — {total} features — bbox {bbox}\n\n")
        # Un bucket por categoría
        f.write("const DATA_VIAL = ")
        json.dump(dict(buckets), f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n\n")
        f.write("const DATA_VIAL_META = ")
        json.dump(meta, f, ensure_ascii=False)
        f.write(";\n")

    print(f"\n✓ Wrote {out_path} ({out_path.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Correr tests para verificar que pasan**

Run: `cd src && uv run pytest ../tests/test_vial.py -v`
Expected: 12 PASSED (10 anteriores + 2 nuevos)

- [ ] **Step 5: Registrar entry-point en `src/pyproject.toml`**

Abrir `src/pyproject.toml` y localizar la sección `[project.scripts]`. Añadir la línea `extract_vial = "extract_vial:main"` debajo de `extract_zoning = "extract_zoning:main"`. Si la sección no existe, crearla.

Verificar el cambio:

Run: `grep extract_vial src/pyproject.toml`
Expected: la línea `extract_vial = "extract_vial:main"` aparece.

- [ ] **Step 6: Commit**

```bash
git add src/extract_vial.py src/pyproject.toml tests/test_vial.py
git commit -m "feat(vial): pipeline extract_vial.py + entry-point + tests"
```

---

### Tarea 5: Smoke test del pipeline (Overpass real)

**Files:**
- Run: `src/extract_vial.py`
- Verify: `visualizer/datos_vial.js`

- [ ] **Step 1: Ejecutar el pipeline contra Overpass real**

Run: `cd src && uv run extract_vial.py`
Expected: termina sin errores. Output muestra ~50,000 raw ways y un breakdown por categoría tipo:

```
  category        count
  --------------  ------
  highway              ~500
  major              ~2000
  minor             ~12000
  local             ~10000
  pedestrian         ~8000
  bike               ~1500
  --------------  ------
  TOTAL             ~34000
```

(Los números exactos dependen de OSM actual. Lo importante: cada categoría > 0 y total entre 20k y 60k.)

- [ ] **Step 2: Inspeccionar el output**

Run: `ls -lh visualizer/datos_vial.js`
Expected: archivo existe, tamaño entre 5 MB y 25 MB.

Run: `head -3 visualizer/datos_vial.js`
Expected: línea de comentario con fecha + `const DATA_VIAL = {"highway":[...]}`

- [ ] **Step 3: Commit el prebuilt (opcional, sigue patrón de Sesión 1.7)**

```bash
git add visualizer/datos_vial.js
git commit -m "build(vial): prebuilt datos_vial.js generado desde OSM"
```

---

### Tarea 6: Integrar overlay vial al `visualizer/index.html`

**Files:**
- Modify: `visualizer/index.html`

El visualizer existente tiene la estructura: `ZONES` dict → `groups[key]` → render polígonos → Layer Control + Legend. Vamos a replicar ese patrón con un dict paralelo `VIAL_TYPES` → `vialGroups[key]` → render LineStrings → secciones extra en Layer Control + Legend.

- [ ] **Step 1: Añadir script tag para `datos_vial.js` después del de zonificación**

Localizar en `visualizer/index.html` la línea (alrededor de la línea 9):

```html
  <script src="datos_zonificacion.js" onerror="window.__noPrebuilt=true"></script>
```

Añadir DEBAJO:

```html
  <script src="datos_vial.js" onerror="window.__noVialPrebuilt=true"></script>
```

- [ ] **Step 2: Definir `VIAL_TYPES` después del bloque `ZONES`**

Localizar el final del dict `ZONES` (línea ~190, después del último item `prk_ramp`). Después del cierre `};` de `ZONES`, añadir:

```javascript
// ══════════════════════════════════════════════════════════════════════════════
// VIAL_TYPES — 6 categorías de red vial CS2 (Sesión 2, 2026-05-15)
// Renderizadas como LineStrings encima del mapa de zonificación.
// ══════════════════════════════════════════════════════════════════════════════
const VIAL_TYPES = {
  highway:    { label: "Highway",         color: "#EF5350", neon: "#FF8A80", weight: 3.5, sect: "Estructurales" },
  major:      { label: "Major Road",      color: "#FFB74D", neon: "#FFCC80", weight: 2.5, sect: "Estructurales" },
  minor:      { label: "Minor Road",      color: "#BCAAA4", neon: "#D7CCC8", weight: 1.4, sect: "Distribución" },
  local:      { label: "Local Street",    color: "#78909C", neon: "#B0BEC5", weight: 0.8, sect: "Distribución" },
  pedestrian: { label: "Pedestrian Path", color: "#26C6DA", neon: "#4DD0E1", weight: 0.6, sect: "No motorizado" },
  bike:       { label: "Bike Lane",       color: "#66BB6A", neon: "#81C784", weight: 0.9, sect: "No motorizado" },
};
```

- [ ] **Step 3: Crear `vialGroups` después de la creación de `groups`**

Localizar el bloque `const groups = Object.fromEntries(...)` (línea ~486). Después del cierre `);` de esa expresión, añadir:

```javascript

// ══════════════════════════════════════════════════════════════════════════════
// VIAL LAYER GROUPS — uno por categoría vial. Sin tier hiding (las vías están
// presentes en todos los zooms igual que las calles del basemap).
// ══════════════════════════════════════════════════════════════════════════════
const vialGroups = Object.fromEntries(
  Object.keys(VIAL_TYPES).map(k => [k, L.layerGroup().addTo(map)])
);
const vialCounts = Object.fromEntries(Object.keys(VIAL_TYPES).map(k => [k, 0]));
```

- [ ] **Step 4: Añadir función `renderVialFeatures` después de `renderRawElements`**

Localizar el cierre `}` de la función `renderRawElements` (línea ~591). Después de esa función, añadir:

```javascript

// ══════════════════════════════════════════════════════════════════════════════
// VIAL RENDER — pinta LineStrings de DATA_VIAL al canvas renderer.
// bridge=yes → weight +0.5 para diferenciar visualmente puentes del Mississippi.
// ══════════════════════════════════════════════════════════════════════════════
function renderVialFeatures() {
  if (typeof DATA_VIAL === "undefined") return 0;
  let count = 0;
  for (const [key, features] of Object.entries(DATA_VIAL)) {
    const meta = VIAL_TYPES[key];
    if (!meta) continue;
    for (const f of features) {
      const w = f.bridge ? meta.weight + 0.5 : meta.weight;
      const line = L.polyline(f.coords, {
        color: meta.neon,
        weight: w,
        opacity: 0.85,
        lineCap: "round",
        lineJoin: "round",
      });
      if (f.name) {
        line.bindPopup(
          `<div style="min-width:140px">` +
          `<b style="color:#ddd;font-size:12px">${f.name}</b><br>` +
          `<span style="color:${meta.neon};font-size:11px">${meta.label}</span>` +
          (f.bridge ? `<br><span style="color:#888;font-size:10px">puente</span>` : "") +
          `</div>`,
          { maxWidth: 240 }
        );
      }
      vialGroups[key].addLayer(line);
      vialCounts[key]++;
      count++;
    }
  }
  return count;
}
```

- [ ] **Step 5: Invocar `renderVialFeatures()` al final de `loadAll`**

Localizar la llamada `finalizeLoad(anyError);` en `loadAll` (línea ~769). Reemplazar:

```javascript
  finalizeLoad(anyError);
}
```

Por:

```javascript
  // Render vial overlay (prebuilt only — no live fetch para vial en Sesión 2)
  const vialN = renderVialFeatures();
  if (vialN > 0) console.log(`[vial] rendered ${vialN.toLocaleString()} features`);

  finalizeLoad(anyError);
}
```

- [ ] **Step 6: Extender el Layer Control con sección vial**

Localizar el bloque del Layer Control (línea ~795):

```javascript
const overlayMap = {};
for (const [key, z] of Object.entries(ZONES)) {
  const dot = `<span style="display:inline-block;width:10px;height:10px;background:${z.neon};` +
              `border-radius:2px;margin-right:7px;opacity:0.9;vertical-align:middle"></span>`;
  overlayMap[dot + z.label] = groups[key];
}
L.control.layers(null, overlayMap, { collapsed: true, position: "topright" }).addTo(map);
```

Reemplazar por:

```javascript
const overlayMap = {};
for (const [key, z] of Object.entries(ZONES)) {
  const dot = `<span style="display:inline-block;width:10px;height:10px;background:${z.neon};` +
              `border-radius:2px;margin-right:7px;opacity:0.9;vertical-align:middle"></span>`;
  overlayMap[dot + z.label] = groups[key];
}
// Vial overlays — separador visual + 6 capas (Sesión 2)
const vialSep = `<span style="display:inline-block;width:100%;border-top:1px solid #2a2d3d;` +
                `margin:6px 0 4px;padding-top:4px;color:#666;font-size:10px;` +
                `text-transform:uppercase;letter-spacing:1px">Vías</span>`;
overlayMap[vialSep] = L.layerGroup();  // separador no-op
for (const [key, v] of Object.entries(VIAL_TYPES)) {
  const dot = `<span style="display:inline-block;width:14px;height:2px;background:${v.neon};` +
              `margin-right:7px;vertical-align:middle"></span>`;
  overlayMap[dot + v.label] = vialGroups[key];
}
L.control.layers(null, overlayMap, { collapsed: true, position: "topright" }).addTo(map);
```

- [ ] **Step 7: Extender la leyenda con sección "Vías"**

Localizar el bloque de la leyenda (línea ~806):

```javascript
const legend = L.control({ position: "bottomleft" });
legend.onAdd = () => {
  const div = L.DomUtil.create("div", "legend");
  let html = "<h4>CS2 Zonificación</h4>";
  let lastSect = "";
  for (const [key, z] of Object.entries(ZONES)) {
    if (z.sect !== lastSect) {
      html += `<div class="lsect">${z.sect}</div>`;
      lastSect = z.sect;
    }
    html += `<div class="li">
      <div class="ldot" style="background:${z.neon}"></div>
      <span class="lname">${z.label}</span>
      <span class="lcount zero" id="lcount-${key}">0</span>
    </div>`;
  }
  div.innerHTML = html;
  return div;
};
legend.addTo(map);
```

Reemplazar por:

```javascript
const legend = L.control({ position: "bottomleft" });
legend.onAdd = () => {
  const div = L.DomUtil.create("div", "legend");
  let html = "<h4>CS2 Zonificación</h4>";
  let lastSect = "";
  for (const [key, z] of Object.entries(ZONES)) {
    if (z.sect !== lastSect) {
      html += `<div class="lsect">${z.sect}</div>`;
      lastSect = z.sect;
    }
    html += `<div class="li">
      <div class="ldot" style="background:${z.neon}"></div>
      <span class="lname">${z.label}</span>
      <span class="lcount zero" id="lcount-${key}">0</span>
    </div>`;
  }
  // Sección Vías
  html += `<h4 style="margin-top:14px">Red Vial</h4>`;
  lastSect = "";
  for (const [key, v] of Object.entries(VIAL_TYPES)) {
    if (v.sect !== lastSect) {
      html += `<div class="lsect">${v.sect}</div>`;
      lastSect = v.sect;
    }
    html += `<div class="li">
      <div class="ldot" style="background:${v.neon};width:14px;height:2px;border-radius:1px"></div>
      <span class="lname">${v.label}</span>
      <span class="lcount zero" id="vcount-${key}">0</span>
    </div>`;
  }
  div.innerHTML = html;
  return div;
};
legend.addTo(map);
```

- [ ] **Step 8: Extender `updateLegendCounts` para incluir conteos viales**

Localizar `updateLegendCounts` (línea ~828):

```javascript
function updateLegendCounts() {
  for (const [key, n] of Object.entries(zoneCounts)) {
    const el = document.getElementById("lcount-" + key);
    if (!el) continue;
    el.textContent = n.toLocaleString();
    el.classList.toggle("zero", n === 0);
  }
}
```

Reemplazar por:

```javascript
function updateLegendCounts() {
  for (const [key, n] of Object.entries(zoneCounts)) {
    const el = document.getElementById("lcount-" + key);
    if (!el) continue;
    el.textContent = n.toLocaleString();
    el.classList.toggle("zero", n === 0);
  }
  for (const [key, n] of Object.entries(vialCounts)) {
    const el = document.getElementById("vcount-" + key);
    if (!el) continue;
    el.textContent = n.toLocaleString();
    el.classList.toggle("zero", n === 0);
  }
}
```

- [ ] **Step 9: Commit**

```bash
git add visualizer/index.html
git commit -m "feat(vial): overlay LineString + Layer Control + leyenda en visualizer"
```

---

### Tarea 7: Browser smoke test

**Files:**
- Run: navegador con `visualizer/index.html`

- [ ] **Step 1: Arrancar servidor local**

Run: `cd visualizer && python -m http.server 8080`

Dejar corriendo en background. La consola debe mostrar `Serving HTTP on :: port 8080`.

- [ ] **Step 2: Abrir el visualizador**

Abrir en el navegador: `http://localhost:8080/index.html`

Esperar a que el loading overlay desaparezca (≤ 5s con prebuilt).

- [ ] **Step 3: Verificación visual**

Confirmar manualmente:

1. **Polígonos de zonificación** — visibles igual que antes (sin regresión).
2. **Líneas viales** — visibles encima de los polígonos. Highways en rojo, major en naranja, minor en marrón claro, local en gris, pedestrian en cyan, bike en verde.
3. **Puentes del Mississippi** — visibles cruzando el río con weight grueso (highway).
4. **Layer Control (arriba derecha)** — al expandirlo, muestra las 13 zonas seguidas del separador "Vías" y las 6 categorías viales toggleables.
5. **Leyenda (abajo izquierda)** — muestra dos secciones: "CS2 Zonificación" y "Red Vial", cada una con conteos.
6. **Console del navegador** — log `[vial] rendered N features` con N entre 20k y 60k. Sin errores rojos.
7. **Pan/zoom fluido** — sin laggy notable (canvas renderer debe seguir manejando todo).

- [ ] **Step 4: Tomar screenshot para documentación**

Run: `cd src && uv run take_screenshots.py`

(Si el script existe y captura el visualizador. Si no, omitir este step.)

- [ ] **Step 5: Apagar el servidor**

Stop el `python -m http.server` lanzado en Step 1.

- [ ] **Step 6: Si todo OK, no hay commit — el browser test no genera archivos**

Si encontraste regresiones, crear una nota en el plan o un issue y arreglar antes de continuar.

---

### Tarea 8: Documentation update

**Files:**
- Modify: `README.md`
- Modify: `README.es.md`
- Modify: `METHODOLOGY.md`

- [ ] **Step 1: Añadir sección "Módulo Vial" a `README.md`**

Localizar la sección donde se describen los módulos completados (probablemente bajo un heading "Modules" o similar). Añadir entrada para el módulo vial con:

```markdown
### Road Network Module (Sesión 2)

Extracts the road network from OpenStreetMap and classifies it into 6 CS2 categories: Highway, Major Road, Minor Road, Local Street, Pedestrian Path, Bike Lane. Renders as LineString overlay on top of the zoning map.

Run: `uv run extract_vial.py`
Output: `visualizer/datos_vial.js` (~10-20 MB, ~30,000 features).
```

- [ ] **Step 2: Replicar en `README.es.md`**

Misma sección traducida al español.

- [ ] **Step 3: Añadir sección al `METHODOLOGY.md`**

Localizar la última sección numerada del methodology. Añadir nueva sección:

```markdown
## N. Red Vial (Sesión 2)

### Modelo

6 categorías mapeadas 1:1 desde `highway=*`:

| Categoría | Tags OSM |
|---|---|
| Highway | motorway, trunk (+ _link) |
| Major Road | primary, secondary (+ _link) |
| Minor Road | tertiary (+ _link), residential, unclassified |
| Local Street | living_street, service |
| Pedestrian Path | pedestrian, footway, path, steps |
| Bike Lane | cycleway |

### Pipeline

- **1 query Overpass** con regex sobre highway → todas las categorías en una pasada
- `vial_classifiers.classify_highway(tags)` → lookup en dict puro
- `linestring_from_way(element)` → coords [[lat, lon], ...] (mínimo 2 puntos)
- Output: `DATA_VIAL` bucketed por categoría + `DATA_VIAL_META`

### Render

LineStrings en `L.polyline()` sobre el mismo Canvas renderer del módulo zonificación. Weight por categoría (3.5px highway → 0.6px pedestrian). `bridge=yes` añade +0.5 al weight para destacar puentes del Mississippi.
```

(Reemplazar `N.` por el número de la siguiente sección disponible en METHODOLOGY.md.)

- [ ] **Step 4: Commit**

```bash
git add README.md README.es.md METHODOLOGY.md
git commit -m "docs(vial): documentar Módulo Red Vial en README + METHODOLOGY"
```

---

### Tarea 9: Cierre de sesión

**Files:**
- Update: `C:\Users\osyanne\Documents\Brain\01-Proyectos\CS2-Mineapolis\📋 Estado del Proyecto.md`
- Create: `C:\Users\osyanne\Documents\Brain\01-Proyectos\CS2-Mineapolis\📦 Sesión 2 — Módulo Vial.md`
- Update: `C:\Users\osyanne\.claude\projects\C--Users-osyanne\memory\proyecto_cs2_mineapolis.md`

- [ ] **Step 1: Marcar Sesión 2 como completada en Estado del Proyecto**

Cambiar la sección `## ⏳ Sesión 2 — Módulo Red Vial (PENDIENTE)` a `## ✅ Sesión 2 — Módulo Red Vial (COMPLETADA 2026-05-15)`. Añadir checklist de tareas completadas debajo.

- [ ] **Step 2: Crear nota de sesión en Obsidian**

Crear `📦 Sesión 2 — Módulo Vial.md` con:
- Objetivo cumplido
- Archivos creados (vial_zones.py, vial_classifiers.py, extract_vial.py, test_vial.py)
- Conteos reales del Overpass run
- Decisiones tomadas
- Próximo paso (Sesión 3 — Servicios)

- [ ] **Step 3: Actualizar memoria persistente**

Editar `proyecto_cs2_mineapolis.md` reemplazando la sección "Estado al cierre de Sesión 1.8" → "Estado al cierre de Sesión 2": Sesión 2 ✅ completada, próximo Sesión 3 — Servicios.

- [ ] **Step 4: Push a GitHub**

```bash
git push origin main
```

---

## Caveats / Decisiones diferidas

- **No se filtran service roads cortas** — pueden generar ruido visual en zonas industriales o estacionamientos. Si molesta, filtrar en una iteración futura por longitud (`shapely.geometry.LineString(coords).length` > N metros) o por ausencia de tag `name`.
- **No se separan puentes en una capa propia** — `bridge=yes` solo afecta el weight. Si se quiere una capa "Puentes" toggleable, añadir un séptimo grupo en `VIAL_TYPES` y duplicar el feature en `extract_vial.py`.
- **No hay clip al boundary real de Minneapolis** — el bbox incluye Edina y St. Louis Park, igual que el módulo zonificación. Esto se podría arreglar en una futura sesión cross-módulo aplicando `shapely.intersection` al boundary OSM de Minneapolis.
- **Modo live fetch desde Overpass NO está implementado para vial** — solo prebuilt (`datos_vial.js`). Si no existe el archivo, el visualizador funciona sin red vial sin errores. Añadir live fetch sigue el mismo patrón que zonificación pero queda fuera de scope de Sesión 2.

---

## Comandos rápidos

```bash
# Generar prebuilt
cd src && uv run extract_vial.py

# Correr tests
cd src && uv run pytest ../tests/test_vial.py -v

# Servir visualizador
cd visualizer && python -m http.server 8080
```
