# Methodology — CS2 Minneapolis Zoning Pipeline

Technical documentation for every design decision in this pipeline.

> **Version 3.0** — This document covers the architecture as of Session 1.7 (May 2026). For the original v1.0 design, see git history.

---

## 1. The Problem: Overpass API 504 Timeouts

The Overpass API is a free, community-run service that allows querying OpenStreetMap data by geographic area. The natural first approach — one query that fetches all zoning types at once — fails consistently for city-sized bounding boxes:

```
HTTP 504 Gateway Timeout
```

This happens because:
- The Minneapolis bbox (`44.86,-93.38,45.05,-93.17`) covers ~350 km²
- A single query requesting all landuse types returns 5-10 MB of JSON
- Public Overpass instances enforce strict timeouts (120-180s) to prevent abuse
- Large queries hit those timeouts even when the server isn't under heavy load

## 2. Solution: Chunked Source Queries

Instead of one mega-query, this pipeline runs 7 source queries in sequence, each one for a specific landuse/building category:

```
mixed_apartments → apartments → landuse_residential → residential_subtypes
→ commercial → office → industrial → parking
```

**Why this works:**
- Each category returns 200-800 KB instead of 5+ MB
- Smaller payloads complete well within the timeout window
- If one category fails, only that category is retried (not everything)
- Progress is visible: users can see each category download in real time

**Trade-off:** 8 round-trips instead of 1, adding ~2-3 minutes of network overhead. This is acceptable because the alternative is unreliable failures.

## 3. The 13-Zone Model (CS2 Oficial Alignment)

Originally (v1.0) the pipeline output ~10 zone types loosely mapped to CS2. In Session 1.6 (2026-05-13) the model was realigned to match the **exact 11 zones** present in CS2 oficial + 2 parking categories for reference.

### Why this realignment matters

CS2 has these zones in the game's painter:

- **Residential (6):** Low Density Housing, Medium Density Row Housing, Medium Density Housing, Mixed Housing, Low Rent Housing, High Density Housing
- **Commercial (2):** Low Density Business, High Density Business
- **Offices (2):** Low Density Offices, High Density Offices
- **Industrial (1):** Industrial Manufacturing

The pre-v1.6 model had only 3 residential tiers (high/med/low), didn't split offices by density, and had no "Mixed Housing" specifically. Now the map reflects what a CS2 player would actually zone in-game.

### The Heuristics

**Residential subtypes — distinguishing Low Rent from Medium/High Density:**

OSM doesn't tag "rent." The pipeline uses a combination of explicit tags + footprint area:

```python
if (tags["building"] in {"public_housing", "council_house"} or
    tags["social_housing"] == "yes"):
    return "low_rent"  # explicit
if 4 <= floors <= 6 and area_m2 >= 1500:
    return "low_rent"  # heuristic: mid-rise + large footprint
if floors >= 7 or building in {"tower", "residential_tower", "skyscraper"}:
    return "high"
```

This isn't perfect — OSM has no canonical "low rent" tag — but it captures the main patterns: large mid-rise apartment blocks (typical low-rent profile) vs. tall residential towers (typical luxury high-density).

**Commercial high-vs-low density:**

Based on the most common patterns in OSM:
- `shop=mall` → always high (a mall is a big-box anchor)
- `tourism=hotel` with ≥4 floors or ≥2000 m² → high
- `amenity` ∈ {cinema, theatre, casino, conference_centre} → high
- Everything else (shops, cafés, restaurants, small commercial) → low

**Office high-vs-low density:**

Simple threshold based on `building:levels` or `building=skyscraper`. ≥4 floors → high.

## 4. Spatial Join for Mixed Housing (Session 1.6.1)

The original Mixed Housing detection (Session 1.6) was tag-based:

```overpass
way["building"="apartments"]["shop"](bbox);
```

This required `shop` and `building=apartments` to be on the **same way** in OSM. In reality, OSM tags commercial POIs as separate **nodes inside** the building polygon — not on the way itself. Result: only 3 Mixed Housing polygons in Minneapolis (clearly wrong).

### The fix: spatial join via `around.set:radius`

Session 1.6.1 added a new source query that uses Overpass's `around.set` spatial operator:

```overpass
[out:json][timeout:120];
(
  node["shop"](bbox);
  node["amenity"~"^(restaurant|cafe|bar|pub|fast_food)$"](bbox);
  node["tourism"="hotel"](bbox);
)->.comm;
(
  way["building"="apartments"](around.comm:5);
  way["building"="residential"](around.comm:5);
  way["building"="mixed_use"](bbox);
);
out body geom;
```

The `(around.comm:5)` filter finds apartment buildings within 5 meters of any commercial POI node. Result: **123 Mixed Housing polygons** detected — a 41× improvement.

### Important syntax note

The query uses **named set** syntax (`->.comm`). The naive `(around:5)` with the implicit `_` set returns 0 results — this was a non-obvious bug we hit during development. Always use named sets for spatial operations spanning multiple statements.

## 5. Footprint Area Computation (Equirectangular Approximation)

To distinguish "block-scale" polygons (50,000 m² landuse) from "individual building" polygons (~150 m²), the pipeline computes polygon area using an equirectangular projection at the centroid:

```python
def polygon_area_m2(coords):
    lat0 = sum(c[0] for c in coords) / len(coords)
    cos_lat0 = math.cos(math.radians(lat0))
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * cos_lat0
    pts = [(c[1] * m_per_deg_lon, c[0] * m_per_deg_lat) for c in coords]
    # Shoelace formula
    n = len(pts); s = 0.0
    for i in range(n):
        x0, y0 = pts[i]; x1, y1 = pts[(i+1) % n]
        s += x0*y1 - x1*y0
    return abs(s) / 2.0
```

Sufficient accuracy at urban scale (city of ~20 km tall). For continent-scale work, use a proper projected CRS via Shapely.

## 6. OSM Element Deduplication Between Categories

OSM has overlapping semantics — a downtown apartment building might appear in multiple source queries simultaneously:
- `apartments` (because `building=apartments`)
- `residential_subtypes` (because also tagged `building=residential`)
- `mixed_apartments` (because near a shop)

If we render all three, the same polygon stacks visually.

**Solution:** Process queries in priority order, maintain a global `seen_ids` set, skip any element already classified:

```python
seen_ids = set()
def add(el, cs2_key):
    if el["id"] in seen_ids: return False
    seen_ids.add(el["id"])
    output[cs2_key].append(make_item(el))
    return True

# Priority order: most specific wins
for el in raw["mixed_apartments"]:    add(el, "res_mixed")
for el in raw["apartments"]:          add(el, classify_apartment(...))
for el in raw["residential_subtypes"]: add(el, ...)
# etc.
```

Same logic mirrored in the JS visualizer for live-mode (no prebuilt data) consistency.

## 7. Multi-Endpoint Rotation with Exponential Backoff

The pipeline rotates across 3 community Overpass endpoints:

| Endpoint | Operator |
|---|---|
| `overpass-api.de` | Official OpenStreetMap Foundation |
| `overpass.kumi.systems` | Kumi Systems (community) |
| `maps.mail.ru/osm/tools/overpass` | Mail.ru Group |

**Retry strategy (in visualizer JS):**
- 3 retries with backoff 2s / 4s / 8s
- Concurrency 2 (two queries in parallel — too many triggers rate limits)
- Final fallback to `corsproxy.io` to bypass CORS limits in the browser

**Retry strategy (in Python `overpass_client.py`):**
- 4 rounds × 3 endpoints = 12 attempts max per query
- Round backoff: 5s / 15s / 30s

These strategies converge on 100% success rate in normal conditions. The one known failure mode: Overpass returning HTTP 200 with an empty `elements` array (silent overload). This is undetectable client-side without semantic validation, which we don't currently do.

## 8. Performance: Canvas Renderer + Tier-Based Hiding

The Leaflet default SVG renderer creates one DOM element per polygon. With 81k polygons:
- Initial render: ~30 seconds
- Pan/zoom: 1-2 second lag per gesture

**Fix 1: Canvas renderer (`preferCanvas: true`)**

Leaflet's Canvas renderer draws all polygons into a single `<canvas>` element. Initial render: ~3 seconds. Pan/zoom: smooth.

**Fix 2: Tier-based polygon hiding**

Most polygons (~64k of 82k) are small individual residences. At zoom 12 (whole-city view) they're 1-pixel dots — visually invisible but still costing render time.

Solution: classify each polygon by footprint area:
- `area ≥ 3000 m²` → "large tier" (landuse blocks) → always visible
- `area < 3000 m²` → "small tier" (individual buildings) → hidden at zoom <14

At low zoom you see the city's silhouette (block-level zoning). At high zoom the individual buildings appear. This matches how the user actually consumes the map.

## 9. Prebuilt Data Mode (`datos_zonificacion.js`)

When `extract_zoning.py` runs, it writes a single `.js` file with 13 arrays (one per CS2 zone) containing all classified polygons. The visualizer detects this file via a `<script>` tag with `onerror` fallback.

**Three load paths in `index.html`:**

```javascript
loadAll() → if hasPrebuiltData()        → loadFromPrebuilt()  (~1s)
         → else if readCache() exists  → render from localStorage (~3s)
         → else                         → fetch Overpass live (~3-5min)
```

The prebuilt file is 27 MB (81k polygons × geometry coords). The localStorage cache is the same data, parsed JSON. The cache fails silently when over the browser's localStorage quota (5-10 MB typical), so cache is mostly useful as a fallback for the next reload (much smaller). The fetch live path is the slowest but always works.

## 10. Session 1.8 Caveat: Microsoft Building Footprints

A future-experimental script `src/extract_msbuildings.py` was added to augment OSM data with Microsoft's [USBuildingFootprints](https://github.com/microsoft/USBuildingFootprints) dataset (5M+ buildings detected from satellite imagery in Minnesota). The goal: fill OSM coverage gaps in suburbs/edge neighborhoods.

**Known issues (rolled back from production):**

1. **Misclassification**: The script uses any polygon ≥3000 m² as a "landuse anchor" for nearest-neighbor classification. But OSM has many large *individual buildings* (a Target store, an industrial warehouse) that are ≥3000 m². Those get used as if they were landuse zones, pulling nearby MS buildings into the wrong classification (houses near Hiawatha Avenue ending up colored as commercial/industrial).

2. **Suggested fix (not yet applied):** Re-query Overpass for ONLY `landuse=*` polygons (pure zoning, no buildings) and use only those as classification anchors. Tighten the "nearest" radius from 500m → 100m.

The script remains in the repo for future improvement. Production runs on OSM-only data.

## 11. Why Not QGIS or PostGIS?

The original v1.0 considered alternatives:

- **QGIS:** GUI-based, excellent for visual workflows, but not scriptable in a reproducible way
- **PostGIS:** Industrial-strength spatial queries, but requires a PostgreSQL server setup
- **GeoPandas:** Python library for geospatial DataFrames, but adds ~500 MB of dependencies (GDAL, Shapely, Fiona)

This pipeline chose none of them for a specific reason: **zero barrier to entry**.

The goal was a tool any CS2 player could run without installing a database. The current pipeline works with `requests` + `tqdm` (and optionally `shapely` for `extract_msbuildings.py`). Anyone with Python can run it in 5 minutes.

The classification accuracy lost by not doing true spatial joins is acceptable for a game map visualization. We use OSM element IDs as proxies for spatial containment, and Overpass's `around.set` for the one place where it really matters (Mixed Housing).

## 12. Adapting to Any City

The pipeline is city-agnostic. Any city with reasonable OSM coverage will work.

**Step 1: Get the bounding box**

Use [Nominatim](https://nominatim.openstreetmap.org/):
```
https://nominatim.openstreetmap.org/search?q=Chicago,IL&format=json&limit=1
```

The response includes a `boundingbox` field: `[south, north, west, east]`.

Note: Overpass QL uses `south,west,north,east` order — swap accordingly.

**Step 2: Consider OSM coverage quality**

North American and Western European cities have excellent OSM coverage including building heights. Cities in other regions may have fewer `building:levels` tags, which will cause most residential to fall back to "low density." This is a data limitation, not a pipeline limitation.

**Step 3: Calibrate thresholds**

Run the pipeline once, open the visualizer, and visually compare against Google Maps satellite view. Adjust thresholds in `src/classifiers.py` if your city has different building patterns:
- `effective_levels` cutoffs for high/med density
- `area_m2` threshold for Low Rent detection
- Commercial high-density signals (mall, hotel, etc.)

See [docs/adapting-to-other-cities.md](docs/adapting-to-other-cities.md) for a complete walkthrough.

## 13. Test Coverage

61 tests across two files (`pytest` in the `tests/` directory):

- **50 classifier tests** (`test_classifiers.py`) — covers all `classify_*` functions, edge cases for height-vs-levels, footprint thresholds, dedup priority
- **11 query sanity tests** (`test_queries.py`) — verifies bbox interpolation, expected source keys, expected CS2 zone keys, spatial join syntax

Run with:
```bash
cd src
uv run --with pytest pytest ../tests/ -v
```

## 14. Red Vial (Sesión 2)

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

108,825 features renderizadas chunked async (5000 features/batch con yield a setTimeout) para evitar bloquear el main thread.
