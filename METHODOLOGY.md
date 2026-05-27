# Methodology — CS2 Minneapolis OSM Toolkit

Technical documentation for every design decision in this toolkit.

> **Version 3.3** — This document covers the architecture as of Session 3 (Services Module) + v3.3 Featured Cities Pack (multi-city architecture, mayo 2026) + the post-Sesión 2 toolkit reorganization (sub-packages `shared/zoning/vial`, prebuilts via GitHub Releases, module pills UI). For the original v1.0 design, see git history.

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

When `extract-zoning` (entry point of `zoning/extract.py`) runs, it writes a single `.js` file with 13 arrays (one per CS2 zone) containing all classified polygons. The visualizer detects this file via a `<script>` tag with `onerror` fallback.

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
- `vial.classifiers.classify_highway(tags)` → lookup en dict puro
- `linestring_from_way(element)` → coords [[lat, lon], ...] (mínimo 2 puntos)
- Output: `DATA_VIAL` bucketed por categoría + `DATA_VIAL_META`

### Render

LineStrings en `L.polyline()` sobre el mismo Canvas renderer del módulo zonificación. Weight por categoría (3.5px highway → 0.6px pedestrian). `bridge=yes` añade +0.5 al weight para destacar puentes del Mississippi.

108,825 features renderizadas chunked async (5000 features/batch con yield a setTimeout) para evitar bloquear el main thread.

## 15. Servicios públicos (Sesión 3)

### Extracción

Una única query Overpass cubre 5 categorías alineadas a las solapas de servicios base de Cities: Skylines 2:

| Bucket | Tags OSM | Geometría esperada |
|---|---|---|
| `health` | `amenity=hospital\|clinic\|doctors\|funeral_directors\|crematorium` + `landuse=cemetery` | Mix polígono + punto |
| `education` | `amenity=school\|university\|college\|kindergarten\|research_institute` + `office=research` | Mayormente polígono |
| `fire` | `amenity=fire_station` | Mix |
| `admin` | `amenity=police\|townhall\|courthouse\|prison\|library\|theatre\|arts_centre\|cinema` + `office=government` + `tourism=museum` | Mix |
| `parks` | `leisure=park\|nature_reserve\|garden\|playground\|sports_centre` | Mayormente polígono |

Timeout 90s, `out body geom` para extraer geometría completa en una sola pasada.

### Filtros aplicados

- **`landuse=cemetery` solo cuenta como `way`.** Los nodes con landuse=cemetery se rechazan — un cementerio sin polígono no aporta información geográfica útil.
- **Subtypes culturales en `admin` requieren `name=*`.** Bibliotecas, teatros, museos, cinemas, arts centres anónimos se filtran para reducir ruido (OSM tiene muchas entradas placeholder sin nombre real).
- **Resto sin filtro adicional.** Hospitales, escuelas, parques se incluyen tal cual.

### Geometría: polígono-preferido + punto-fallback

Cada entidad OSM aparece **una vez** en el output. La función `infer_geometry_kind(element)`:

1. Si `element.type === "node"` → `"point"` (usa lat/lon directo)
2. Si `element.type === "way"` con geometría ≥4 nodos Y primer==último → `"polygon"`
3. Sino → `"point"` (usa primer nodo como anchor)

Esto evita duplicación cuando la misma entidad tiene representación tanto como node como way en OSM, y elige la representación más informativa (polígono > punto).

### Rendering

- **Polígonos:** `L.polygon` con Canvas renderer compartido (`L.canvas()` único para todos), fill opacity 0.35, stroke 1.5px opacity 0.9. **Siempre visibles** independiente del zoom.
- **Markers (puntos):** `L.divIcon` con círculo de 22px (background = color del bucket, char = letra H/E/B/A/P en blanco). **Ocultos en `zoom < 12`**, visibles en `zoom ≥ 12`. Tier-hiding integrado al callback `map.on("zoomend")` existente.
- **Popups:** name del feature (color del bucket) + label CS2 + subtype OSM + tags raw colapsables en `<details>`. Todo el contenido pasa por `escHtml` — patrón XSS-safe existente del módulo zoning.

### Async chunked render

Inicialmente el render era sincrónico asumiendo <1000 features. La realidad: bbox de Minneapolis suelta **~2273 features** (1573 son parques — playgrounds, gardens, sports centres). El render sincrónico bloqueaba el thread del browser ~10-20s, impidiendo que el loading overlay pintara.

**Fix:** mismo patrón que `renderVialFeatures` — async chunked con `await new Promise(r => setTimeout(r, 0))` cada 250 features. Tiempo total de init: ~4 segundos con paint intermedio del loading overlay.

### Diferido a Sesión 4 — Módulo Infraestructura

Tres capas de servicios CS2 que NO se incluyeron en Sesión 3 porque requieren fuentes no-OSM:

| Capa CS2 | Por qué OSM no alcanza | Fuente recomendada |
|---|---|---|
| Electricidad | OSM cubre ~30-50% subestaciones, casi nada distribución | EIA (US Energy Info Admin) |
| Agua y saneamiento | OSM tiene asset grandes pero faltan tuberías de distribución | MN GIS Commons |
| Gestión de residuos | OSM tiene <20 features útiles en Minneapolis | opendata.minneapolismn.gov |

**Trabajo adicional requerido:** `src/services/sources/` con cliente por fuente (no solo overpass_client), `pyproj` para reproyección MN State Plane → WGS84, reconciliación de duplicados OSM↔EIA.

### Decisiones documentadas

- **Design spec:** [`docs/plans/2026-05-16-modulo-servicios.md`](docs/plans/2026-05-16-modulo-servicios.md)
- **Implementation plan:** [`docs/plans/2026-05-16-modulo-servicios-implementation.md`](docs/plans/2026-05-16-modulo-servicios-implementation.md)
- **Tests:** 54 tests pytest pasando (12 zones + 36 classifiers + 6 extract)

---

## Sección 16 — Multi-city architecture (v3.3, mayo 2026)

Tras Sesiones 1-3 con scope Minneapolis-only, el toolkit se generalizó para
soportar múltiples ciudades via Featured Cities Pack.

### Cambios estructurales

- **Registro `cities.json`** (raíz del repo): single source of truth para qué
  ciudades existen, con bbox + center + zoom + tagline + locale por entry.
- **Manifest per-city** (`visualizer/cities/<slug>/manifest.json`): declara qué
  módulos están generados para esa ciudad y sus hashes (sha256 trunco para
  cache busting). Se actualiza automáticamente cada vez que un extract corre.
- **Pipeline `--city` flag**: los 3 extracts (zoning/vial/services) aceptan
  `--city <slug>` que resuelve bbox desde el registro. `--bbox X --slug Y`
  queda como escape hatch para ciudades no registradas.
- **Visualizer refactor**: `index.html` legacy → `map.html` (lee `?city=`,
  inyecta scripts dinámicamente desde `manifest.json`). Nueva `index.html` es
  landing page generada por `generate-landing` script.

### Scope Phase 1

- Minneapolis preserva los 3 módulos (hero/legacy).
- 3 ciudades adicionales (Amsterdam, Madison, Charleston) entran solo con
  zoning. Vial y services on-demand vía GitHub Issues post-launch.
- Manhattan y Tokyo se incluyeron originalmente en v3.3 pero se removieron
  en v3.3.2 (2026-05-18) para enfocar el set en cities con request real de la
  community + Amsterdam como referencia de fine-grained EU tagging.
- En v3.3.3 (2026-05-18 PM) se incorporan **Trondheim (Norway)** y
  **Mafra, SC (Brazil)** como las primeras dos cities entrantes por
  community city-request (Issues #5 y #6). A partir de v3.3.3 el template
  de city-request limita el scope a **zoning-only** mientras se amplía
  la cobertura geográfica; vial/services para nuevas cities quedan pausados.

### Deferreds (Phase 2+)

- Rename del repo a `cs2-osm-toolkit` (espera caída de tráfico Reddit v3.2).
- Heightmap generation pipeline (Phase 3 — valida demanda con Featured
  Cities primero; CityTimelineMod fork confirma demanda implícita).
- Reapertura de vial/services para nuevas city-requests cuando la cobertura
  de zoning alcance ≥10 cities.
- Promoción de cities zoning-only a fully-featured (cuando acumulen 5+
  requests por vial/services).

---

## Sección 17 — Generic buildings: spatial-join + heurística (v3.3.4)

### Problema

Al procesar Mafra, SC (Brasil) en v3.3.3 quedó claro que el extractor de zoning
solo recogía **24%** de los buildings tagged en OSM (105 / 427 ways). El resto
estaba como `building=yes` sin más contexto — el extractor los ignoraba porque
no encajaban en ninguna categoría específica (apartments, residential_subtypes,
commercial, office, industrial).

Esto reflejaba un patrón conocido de OSM: en regiones con cobertura sparse
(small-town LATAM, África, parte de Asia) la mayoría de los building footprints
están como `building=yes` por imports masivos sin enriquecimiento posterior.
Para esas zonas, una visualización de zoning honesta requería poder **inferir**
la zona de los footprints sin tipificar.

### Solución

Nuevo paso 8 del pipeline `extract-zoning`:

1. **Nueva query `generic_buildings`** que recoge `way["building"="yes"]` y
   `relation["building"="yes"]` del bbox.
2. **Dedup global por OSM id** — buildings ya capturados por queries
   específicas se ignoran (los tags específicos siempre ganan).
3. **Spatial join contra landuse polygons** — para cada generic building:
   - Construir un `STRtree` con los polígonos `landuse=*` ya extraídos por
     queries existentes (residential, commercial, retail, industrial, office).
   - Buscar el polígono que contiene el centroide del building.
   - Si hay match → clasificar por `LANDUSE_TO_CS2_KEY` (mapa landuse→CS2 key).
4. **Heurística de área como fallback** — si no hay landuse que lo contenga:
   - `< 300 m²`   → `res_low_house` (casa pequeña)
   - `300–1500 m²` → `res_med` (edificio mediano)
   - `≥ 1500 m²` → `industrial` (footprint grande sin contexto = nave/galpón)

### Impacto medido (re-extract 2026-05-18 PM)

| City | v3.3.3 polygons | v3.3.4 polygons | Δ | generic+ (landuse / area) |
|------|-----------------|-----------------|---|---------------------------|
| Minneapolis | 81,825 | 204,470 | +150% | 122,633 (57k / 66k) |
| Amsterdam | 89,228 | 137,559 | +54% | 48,331 (42k / 6k) |
| Madison | 36,738 | 55,889 | +52% | 19,151 (17k / 2k) |
| Charleston | 14,495 | 31,957 | +120% | 17,461 (9k / 8k) |
| Trondheim | 40,339 | 43,499 | +8% | 3,160 (1.4k / 1.8k) |
| Mafra | 105 | 431 | +310% | 326 (4 / 322) |

**Lectura:** ciudades con landuse polygons granulares (US/EU) ganan
clasificación por spatial join (lo más confiable). Ciudades con landuse
sparse (LATAM small-town) dependen más de la heurística de área. En todas
las ciudades el delta es positivo — el algoritmo es defensivo (solo añade
buildings no clasificados antes; nunca sobreescribe).

### Diseño defensivo

- **Tags específicos siempre ganan**: si una way tiene `building=apartments`,
  pasa por `classify_apartment` y nunca llega al paso generic.
- **Cero falsos positivos en cities granulares**: en Mpls los apartments,
  houses, terraces, etc. ya están bien clasificados por su tag específico.
- **Honestidad de signal**: el output incluye `generic+` con breakdown
  landuse vs área heurística — el usuario puede ver qué fracción del map
  viene de inferencia.

Ver implementación: `src/zoning/extract.py` (`_process_generic_buildings`),
`src/zoning/classifiers.py` (`classify_generic_building_by_area`,
`LANDUSE_TO_CS2_KEY`).

---

## Sección 18 — External buildings augmentation: Google Open Buildings (v3.3.5)

### Problema

El generic-buildings pass de v3.3.4 extrajo el 100% de los `building=yes`
en Mafra (326 polygons clasificados) — y aun así la ciudad quedó con apenas
431 polygons totales. Causa: **OSM literalmente solo tiene 427 buildings
tagged en el bbox**. Mafra tiene ~55k habitantes; era estructuralmente
imposible que OSM contara más buildings sin contribución upstream.

### Solución: ingest ML-detected footprints

Las fuentes globales de building footprints ML-detectados (Microsoft, Google,
Overture) tienen **>1 billón de buildings** que NO están en OSM. Para zonas
con OSM sparse, son el complemento natural — geometrías sin tipo, exactamente
el input para el algoritmo v3.3.4.

Se elige **Google Open Buildings v3** sobre Microsoft Global por:
- Modelo ML más reciente (1.8B globales vs 1B de MS)
- Foco explícito en LATAM/África/SE-Asia (target del lanzamiento humanitario)
- Confidence scores por building (0.65–1.0) → permite filtrar ruido
- Licencia dual CC BY 4.0 + ODbL (más permisiva que solo ODbL)

### Pipeline (`extract-google-buildings`)

1. **S2 cell lookup**: calcula con `s2sphere` qué S2 cell L6 (~50–100k km²)
   toca el bbox. Para bboxes urbanos típicos, 1 cell suele bastar.
2. **Download cacheado**: trae los `<token>_buildings.csv.gz` de
   `storage.googleapis.com/open-buildings-data/v3/polygons_s2_level_6_gzip_no_header/`.
   Cache vive en `.cache/google_open_buildings/` (gitignored).
3. **Landuse polygons via Overpass**: ejecuta las 4 queries de landuse
   (residential/commercial/industrial/office) para construir el STRtree
   del spatial join. Reusa `zoning.zones.build_queries`.
4. **Stream + filter**: parsea el CSV.gz línea por línea, descarta
   buildings fuera del bbox o con confidence < threshold (default 0.75).
5. **Classify**: mismo algoritmo que `_process_generic_buildings` —
   spatial join contra landuse, fallback heurística de área.
6. **Output**: `visualizer/cities/<slug>/datos_external_buildings.js`
   con arrays `DATA_EXT_<ZONE>` paralelos a los de zoning. Manifest
   gana entry `external_buildings`.

### Integración con el visualizer

`map.html` carga el módulo si está en el manifest, y `PREBUILT_DATASETS`
concatena `DATA_<ZONE>` (OSM) + `DATA_EXT_<ZONE>` (Google) en una sola
lista por zona. Los polígonos Google llevan `src: "google"` + `conf`,
visible en el popup. Toggle de layers funciona normalmente para ambos.

### Impacto medido (Mafra primero, 2026-05-18 PM)

| Métrica | OSM-only (v3.3.4) | + Google augment (v3.3.5) | Δ |
|---|---|---|---|
| Polygons totales | 431 | **35,552** | **+82×** |
| res_low_house | 182 | 33,428 | +33,246 |
| res_med | 113 | 1,798 | +1,685 |
| industrial | 51 | 241 | +190 |
| Por landuse spatial join | 4 (de 326) | +96 (de 35,121) | |
| Por área heurística | 322 | +35,025 | |
| File size | 28 KB | **11.8 MB** | 420× |
| OSM building density | 5.8/km² | 480/km² | 82× |

**Lectura:** Mafra ahora se ve poblada. El mapa muestra ~35.5k footprints
ML-clasificados, dominados por low-density housing (consistente con
small-town brasileña de viviendas <300 m²). Sin contribución a OSM,
la ciudad pasó de "casi vacía" a "densamente poblada" en 2 minutos de
runtime.

### Diseño defensivo

- **OSM siempre gana**: si una way tiene un building específico en OSM
  (`building=house`), el módulo zoning ya lo capturó en la pasada anterior.
  Google añade buildings que NO estaban en OSM. No hay sobreescritura.
- **Confidence threshold opt-in**: el flag `--min-confidence` permite
  ajustar el filtro de ruido. Default 0.75 es conservador.
- **Source visible en popup**: el usuario puede distinguir OSM-derived
  de Google-ML en cualquier polígono. Honestidad sobre la incertidumbre.

### Casos de uso futuros

Cualquier city-request en zona OSM sparse:
- Latin America small-town
- Africa subsaharian urbanism
- SE Asia secondary cities
- Rural areas anywhere

El operador run-once `extract-google-buildings --city <slug>` añade el
módulo de ML buildings. El visualizer detecta el manifest y los renderiza.

Ver implementación: `src/zoning/extract_google_buildings.py` (script
nuevo + entry point `extract-google-buildings`).

Ver spec: `docs/specs/2026-05-17-featured-cities-pack-design.md`
Ver plan: `docs/plans/2026-05-17-featured-cities-pack.md`

---

## 15. Official zoning layer (added 2026-05-24)

OSM-derived zoning is land use detection (what physically exists). For cities
that publish their official zoning maps, the toolkit offers an alternative
overlay sourced from city open data portals — selectable in the visualizer's
Zoning legend (OSM-derived ↔ Official ↔ Comparison).

### Pluggable architecture

Each supported city declares a Python `Source` module in
`src/official_zoning/sources/` + a YAML mapping table in
`src/official_zoning/mappings/`. Adding a new US city is one source module +
one YAML; no core refactor.

### Pipeline

1. Download shapefile from city open data portal (cached in `~/.cache/cs2-osm-toolkit/official_zoning/`)
2. Parse with geopandas + pyogrio
3. Reproject to WGS84 (EPSG:4326)
4. Spatial filter by city bbox (from `cities.json`)
5. Translate native zoning codes to 13 CS2 zone keys via YAML mapping
6. Emit `visualizer/cities/<slug>/datos_zonificacion_official.js`
7. Register module in per-city `manifest.json`

### Sources shipped in this release

- **Minneapolis** — Mpls Municipal Code Chapter 530 (~25 districts)
- **New York** — NYC Zoning Resolution / ZoLA (~70 districts)

### Known limitation

The `DATA_URL` constants in source modules are placeholders that need
human-loop verification against the live portals (CDNs block automated URL
discovery). To activate: open the portal in a browser, capture the resolved
shapefile URL from DevTools, update the constant, and re-run the extraction
CLI. The full pipeline is tested with mocked GeoDataFrames; the network path
is exercised opt-in via `pytest -m network`.

---

## 16. Transit overlay (added 2026-05-25)

A 4-category transit overlay sourced from OpenStreetMap route relations.
A single Overpass query fetches all `route=light_rail|train|tram|bus`
relations in the city bbox; each relation becomes one polyline (multi-way
relations are concatenated where members touch; disjoint segments emit the
longest continuous piece).

### Category mapping

| OSM route | Network/name hint | CS2 category |
|---|---|---|
| `light_rail` | — | LRT |
| `tram` | — | LRT (display) |
| `train` / `commuter_rail` | — | Commuter Rail |
| `bus` | `network=METRO` or `name` matches `METRO X Line` | BRT |
| `bus` | (other) | Bus |

### Sources shipped

Minneapolis (Metro Transit, 297 routes for the city bbox including 5 LRT,
4 commuter rail, and ~288 bus routes). METRO Rapid BRT lines currently fall
under "Bus" due to OSM tag variance — to be refined in v1.1.

### Activation

The visualizer activates the "Transporte" tile automatically when the per-city
manifest declares the `transporte` module. The tile starts disabled (with a
lock icon) on cities that haven't generated transit data; once
`window.transporteLoaded()` fires after lazy-loading `datos_transporte.js`,
it patches the MODULES registry and the existing toggle infrastructure handles
clicks via `wireUpModuleControls` / `toggleModule` / `applyModuleState`.

### Performance note

The Mpls `datos_transporte.js` is ~4 MB (297 routes with full member geometry).
Lazy-loaded after primary render so it doesn't block initial paint. Future
optimization options: coordinate decimation, way-filtering by relevant network,
or removing routes that fall outside the visible bbox.
