# Sesión 3 — Módulo Servicios — Design Spec

> **Estado:** Design completo derivado de brainstorming. Pendiente: usar `superpowers:writing-plans` para producir el plan de implementación paso a paso (tasks con checkboxes).

**Goal:** Extraer servicios públicos de Minneapolis desde OpenStreetMap, alinearlos a las 5 solapas de servicios base de Cities: Skylines 2 que tienen buena cobertura OSM, y renderizarlos como overlay sobre el visualizador existente.

**Architecture:** Mismo patrón que el módulo vial (Sesión 2): un sub-paquete Python (`src/services/`) que produce un único `datos_servicios.js` prebuilt, cargado por el `visualizer/index.html` ya existente. El visualizer extiende su Layer Control y leyenda con una sección **"Servicios"** debajo de la sección "Vías". Sin visualizer separado.

**Tech Stack:** Python 3.11 + uv | Overpass API (multi-endpoint con `shared.overpass_client.query_with_retry`) | Leaflet.js (Canvas renderer para polígonos, divIcon markers para puntos) | CartoDB Dark Matter basemap | pytest

**Fecha:** 2026-05-16
**Predecesor:** [Sesión 2 — Módulo Red Vial](./2026-05-15-modulo-vial.md)

---

## Decisiones del brainstorming

| # | Decisión | Valor |
|---|---|---|
| 1 | Propósito | Mezcla por categoría — algunas son checklist (Salud, Bomberos), otras referencia visual (Parques) |
| 2 | Scope final | **5 capas** alineadas a solapas CS2 base con buena cobertura OSM |
| 3 | Manejo geometría | Polígono-preferido + punto-fallback. Cada entidad aparece UNA vez |
| 4 | Filtros | `name=*` requerido solo para subtypes culturales dentro de `admin` (library, theatre, museum, cinema, arts_centre). Cementerios solo polígonos (sin nodes). Resto sin filtro |
| 5 | Estilo marcador | Círculo de color + 1 char (estilo B del mockup) |
| 6 | Letras | H / E / B / A / P — sin choques |
| 7 | Paleta | Paleta "Servicio" diferenciada (subset de la paleta C del mockup) |
| 8 | Tier-hiding | Polígonos siempre visibles. Markers de nodes ocultos en zoom < 12, visibles en zoom ≥ 12 |
| 9 | Tamaño marker | 22px diámetro, borde blanco 2px, texto 11px bold |
| 10 | Popup | Reusa patrón XSS-safe de zoning (`escHtml`) — name + subtype + tags raw colapsables |
| 11 | Layer Control | Nueva sección "Servicios" con 5 checkboxes + checkbox padre "Servicios (todos)" |
| 12 | Diferido a Sesión 4 | Electricidad + Agua y saneamiento + Gestión de residuos (requieren EIA + MN GIS, no OSM) |
| 13 | Descartado | Lugares de culto (no encajan en estructura CS2). Bibliotecas/museos/teatros entran en bucket `admin` |

---

## Las 5 capas

| Clave | Capa CS2 | Tags OSM | Letra | Color |
|---|---|---|---|---|
| `health` | Atención sanitaria y funeraria | `amenity=hospital\|clinic\|doctors\|funeral_directors\|crematorium` + `landuse=cemetery` | **H** | `#D81B60` |
| `education` | Educación e investigación | `amenity=school\|university\|college\|kindergarten\|research_institute` + `office=research` | **E** | `#FDD835` |
| `fire` | Bomberos | `amenity=fire_station` | **B** | `#E64A19` |
| `admin` | Policía y administración | `amenity=police\|townhall\|courthouse\|prison\|library\|theatre\|arts_centre\|cinema` + `office=government` + `tourism=museum` | **A** | `#1E88E5` |
| `parks` | Parques | `leisure=park\|nature_reserve\|garden\|playground\|sports_centre` | **P** | `#43A047` |

**Trade-off conocido en `admin`:** una library, un museo y un police HQ comparten color azul y char "A". Distinción solo en el popup (name + subtype). Aceptado conscientemente como precio por mantener 5 buckets alineados a CS2 sin proliferación de capas.

---

## Estructura de archivos

### Crear

- `src/services/__init__.py`
- `src/services/zones.py` — `SERVICES_LABELS`, `SERVICES_COLORS`, `MINNEAPOLIS_BBOX` reexport, `build_services_query(bbox)`
- `src/services/classifiers.py` — `classify_service(tags, element_type)`, `infer_geometry_kind(element)`
- `src/services/extract.py` — pipeline CLI con entry point `extract-services`
- `tests/services/__init__.py`
- `tests/services/test_zones.py` — labels, colors, query builder
- `tests/services/test_classifiers.py` — clasificación, geometría, filtros `name=*`
- `tests/services/test_extract.py` — integración con fixture mock de Overpass

### Modificar

- `visualizer/index.html` — añadir `<script src="datos_servicios.js" onerror="window.__noServicesPrebuilt=true"></script>`, definir `SERVICES_TYPES`, `serviceGroups`, funciones `renderServicesFeatures()`, `makeServiceIcon()`, `buildServicePopup()`, `applyZoomVisibility()`, integrar a Layer Control y leyenda
- `src/pyproject.toml` — añadir `[project.scripts]` entry `extract-services = "services.extract:main"`
- `.gitignore` — añadir `datos_servicios.js` y `visualizer/datos_servicios.js` (mismo patrón que vial/zoning prebuilts)
- `README.md` y `README.es.md` — sección nueva "Módulo Servicios" (badges, descripción, comando)
- `METHODOLOGY.md` — sección 15 "Módulo Servicios" (después de Red Vial)

### NO tocar

- `src/shared/overpass_client.py` — reusamos `query_with_retry` tal cual
- `src/vial/*`, `src/zoning/*` — módulos previos quedan intactos
- Tests existentes de vial y zoning — siguen pasando sin modificación

---

## Modelo Python (`src/services/zones.py`)

```python
"""
services/zones.py — Modelo de servicios públicos CS2 (Sesión 3, 2026-05-16)
=============================================================================
5 capas alineadas a las solapas de servicios base de Cities: Skylines 2 con
buena cobertura OpenStreetMap:

  health      → Atención sanitaria y funeraria (hospitales + cementerios)
  education   → Educación e investigación (schools + research labs)
  fire        → Bomberos
  admin       → Policía y administración (incl. landmarks culturales)
  parks       → Parques (incl. playgrounds y sports centres)

Diseño de query:
  - UNA sola query Overpass cubre las 5 capas con regex sobre amenity/leisure
  - Incluye también office=government, office=research, tourism=museum
  - out body geom: cada way trae su geometría completa en una pasada
  - timeout 90s (esperado ~600-900 features en bbox de Minneapolis)
"""

SERVICES_LABELS = {
    "health":    "Atención sanitaria y funeraria",
    "education": "Educación e investigación",
    "fire":      "Bomberos",
    "admin":     "Policía y administración",
    "parks":     "Parques",
}

SERVICES_COLORS = {
    "health":    {"color": "#D81B60", "char": "H"},
    "education": {"color": "#FDD835", "char": "E"},
    "fire":      {"color": "#E64A19", "char": "B"},
    "admin":     {"color": "#1E88E5", "char": "A"},
    "parks":     {"color": "#43A047", "char": "P"},
}

# Reexport — pipelines de zoning, vial y services comparten bbox
MINNEAPOLIS_BBOX = "44.86,-93.38,45.05,-93.17"


def build_services_query(bbox: str) -> str:
    """
    Una query Overpass QL que devuelve todos los servicios en los 5 buckets.
    """
    amenity_regex = (
        "hospital|clinic|doctors|funeral_directors|crematorium|"
        "school|university|college|kindergarten|research_institute|"
        "fire_station|"
        "police|townhall|courthouse|prison|library|theatre|arts_centre|cinema"
    )
    leisure_regex = "park|nature_reserve|garden|playground|sports_centre"

    return f"""
[out:json][timeout:90];
(
  node["amenity"~"^({amenity_regex})$"]({bbox});
  way["amenity"~"^({amenity_regex})$"]({bbox});

  node["leisure"~"^({leisure_regex})$"]({bbox});
  way["leisure"~"^({leisure_regex})$"]({bbox});

  way["landuse"="cemetery"]({bbox});

  node["office"~"^(government|research)$"]({bbox});
  way["office"~"^(government|research)$"]({bbox});

  node["tourism"="museum"]({bbox});
  way["tourism"="museum"]({bbox});
);
out body geom;
""".strip()
```

---

## Clasificación (`src/services/classifiers.py`)

```python
# Single source of truth — mapeo tag → categoría
TAG_TO_CATEGORY = {
    # health (sanitaria + funeraria)
    ("amenity", "hospital"):           "health",
    ("amenity", "clinic"):             "health",
    ("amenity", "doctors"):            "health",
    ("amenity", "funeral_directors"):  "health",
    ("amenity", "crematorium"):        "health",
    ("landuse", "cemetery"):           "health",   # solo ways
    # education + research
    ("amenity", "school"):             "education",
    ("amenity", "university"):         "education",
    ("amenity", "college"):            "education",
    ("amenity", "kindergarten"):       "education",
    ("amenity", "research_institute"): "education",
    ("office",  "research"):           "education",
    # fire
    ("amenity", "fire_station"):       "fire",
    # admin (incluye landmarks culturales)
    ("amenity", "police"):             "admin",
    ("amenity", "townhall"):           "admin",
    ("amenity", "courthouse"):         "admin",
    ("amenity", "prison"):             "admin",
    ("amenity", "library"):            "admin",
    ("amenity", "theatre"):            "admin",
    ("amenity", "arts_centre"):        "admin",
    ("amenity", "cinema"):             "admin",
    ("office",  "government"):         "admin",
    ("tourism", "museum"):             "admin",
    # parks
    ("leisure", "park"):               "parks",
    ("leisure", "nature_reserve"):     "parks",
    ("leisure", "garden"):             "parks",
    ("leisure", "playground"):         "parks",
    ("leisure", "sports_centre"):      "parks",
}

# Subtypes que requieren name=* (solo culturales en admin)
NAME_REQUIRED_SUBTYPES = {
    ("amenity", "library"),
    ("amenity", "theatre"),
    ("amenity", "arts_centre"),
    ("amenity", "cinema"),
    ("tourism", "museum"),
}


def classify_service(tags: dict, element_type: str) -> str | None:
    """
    Devuelve la categoría (health|education|fire|admin|parks) o None.

    Reglas:
    - Itera los tags y devuelve la PRIMERA categoría matched (determinístico
      por orden de iteración de dict en Python 3.7+)
    - landuse=cemetery solo cuenta si element_type=='way' (cementerios sin
      polígono no aportan información)
    - Subtypes culturales (library, theatre, museum, cinema, arts_centre)
      requieren tag name=*
    """
    for key, value in tags.items():
        cat = TAG_TO_CATEGORY.get((key, value))
        if cat is None:
            continue
        if (key, value) == ("landuse", "cemetery") and element_type == "node":
            return None
        if (key, value) in NAME_REQUIRED_SUBTYPES and not tags.get("name"):
            return None
        return cat
    return None


def infer_geometry_kind(element: dict) -> str:
    """
    Devuelve 'polygon' si el way está cerrado (>=4 nodos, primer==último),
    sino 'point'. Nodes siempre son 'point'.
    """
    if element["type"] != "way":
        return "point"
    geom = element.get("geometry", [])
    if len(geom) < 4:
        return "point"
    first, last = geom[0], geom[-1]
    if first["lat"] == last["lat"] and first["lon"] == last["lon"]:
        return "polygon"
    return "point"
```

---

## Pipeline (`src/services/extract.py`)

Flujo:

```
1. build_services_query(MINNEAPOLIS_BBOX)
        ↓
2. shared.overpass_client.query_with_retry(q)  [3 reintentos multi-endpoint]
        ↓
3. for element in data["elements"]:
       cat  = classify_service(element["tags"], element["type"])
       if cat is None: skip
       kind = infer_geometry_kind(element)
       feat = make_feature(element, cat, kind)
       buckets[cat][kind].append(feat)
        ↓
4. Escribir visualizer/datos_servicios.js (dos objetos JSON-as-JS)
        ↓
5. Imprimir resumen: "✓ 5 buckets, NNN features (PPP polygons + QQQ points)"
```

`make_feature(element, cat, kind)` devuelve:
```python
{
    "name":    tags.get("name"),  # puede ser None
    "subtype": tags.get("amenity") or tags.get("leisure") or tags.get("landuse")
               or tags.get("office") or tags.get("tourism"),
    "coords":  [[lat,lon], ...] if kind == "polygon" else None,
    "coord":   [lat, lon] if kind == "point" else None,
    "tags":    dict(tags),  # raw para popup
}
```

**Resolución de coordenadas para `coord` (kind == "point"):**
- Si `element["type"] == "node"`: usar `(element["lat"], element["lon"])`
- Si `element["type"] == "way"` con geometría corta (<4 nodos): usar el primer nodo de `element["geometry"]` como anchor

Esto es un edge case raro (ways muy cortos clasificables) pero hay que tenerlo definido para evitar `KeyError` en pipeline.

---

## Formato `visualizer/datos_servicios.js`

```javascript
// Generated by extract-services. Do not edit manually.
// Generated: 2026-05-16T...

const DATA_SERVICES_POLYGONS = {
  health:    [/* {name, subtype, coords, tags}, ... */],
  education: [...],
  fire:      [...],
  admin:     [...],
  parks:     [...],
};

const DATA_SERVICES_POINTS = {
  health:    [/* {name, subtype, coord, tags}, ... */],
  education: [...],
  fire:      [...],
  admin:     [...],
  parks:     [...],
};
```

Dos objetos separados por geometría — el frontend itera distinto sobre cada uno.

---

## Frontend (`visualizer/index.html`)

### Script tag

```html
<script src="datos_servicios.js" onerror="window.__noServicesPrebuilt=true"></script>
```

### Constantes

```javascript
const SERVICES_TYPES = {
  health:    { label: "Atención sanitaria y funeraria", color: "#D81B60", char: "H" },
  education: { label: "Educación e investigación",      color: "#FDD835", char: "E" },
  fire:      { label: "Bomberos",                        color: "#E64A19", char: "B" },
  admin:     { label: "Policía y administración",        color: "#1E88E5", char: "A" },
  parks:     { label: "Parques",                         color: "#43A047", char: "P" },
};

const SERVICES_POINT_ZOOM_THRESHOLD = 12;  // markers ocultos en zoom < 12

const serviceGroups = {};
for (const key of Object.keys(SERVICES_TYPES)) {
  serviceGroups[key] = L.layerGroup();
}
```

### Funciones de render

`renderServicesFeatures()`:
- Bail-out si `window.__noServicesPrebuilt`
- Itera `DATA_SERVICES_POLYGONS[key]` → `L.polygon(coords, {color, weight:1.5, opacity:0.9, fillColor, fillOpacity:0.35, renderer: L.canvas()})` con popup
- Itera `DATA_SERVICES_POINTS[key]` → `L.marker(coord, {icon: makeServiceIcon(type)})` con popup
- Llama `applyZoomVisibility()` para estado inicial

`makeServiceIcon(type)`:
- `L.divIcon` con HTML inline: círculo de 22px, borde blanco 2px, char centrado, shadow

`buildServicePopup(feat, key)`:
- HTML escapado con `escHtml` (ya existente en zoning)
- Estructura: nombre en bold con color de categoría, label + subtype, `<details>` con tags raw

`applyZoomVisibility()`:
- En `map.on("zoomend")`
- Si zoom ≥ 12: markers visibles. Si zoom < 12: markers removidos de su layerGroup (polígonos siempre quedan)

### Layer Control y leyenda

- Sección "Servicios" en el panel lateral debajo de "Vías"
- 5 checkboxes (label + swatch + char) + checkbox padre "Servicios (todos)"
- Leyenda igual a vial: lista de 5 items con dot + label

---

## Tests

### `tests/services/test_zones.py`
- `test_services_labels_has_five_keys`
- `test_services_colors_match_labels`
- `test_query_contains_all_amenities` (hospital, school, fire_station, police, library, museum, etc.)
- `test_query_contains_leisure`
- `test_query_contains_cemetery_only_ways` (sí `way["landuse"="cemetery"]`, no `node`)
- `test_query_contains_office_government_and_research`
- `test_query_contains_tourism_museum`
- `test_bbox_reexport_matches_zoning`

### `tests/services/test_classifiers.py`
- `test_hospital_classifies_to_health`
- `test_cemetery_node_is_rejected`
- `test_cemetery_way_is_health`
- `test_library_without_name_rejected`
- `test_library_with_name_is_admin`
- `test_museum_with_name_is_admin`
- `test_school_without_name_still_classified` (name solo requerido en culturales)
- `test_office_government_is_admin`
- `test_office_research_is_education`
- `test_playground_is_parks`
- `test_irrelevant_tag_is_none` (e.g., amenity=restaurant)
- `test_closed_way_is_polygon`
- `test_open_way_is_point`
- `test_short_way_is_point` (<4 nodos)
- `test_node_is_point`

### `tests/services/test_extract.py`
- `test_extract_writes_two_objects` (con fixture mock de Overpass, valida que datos_servicios.js contenga `DATA_SERVICES_POLYGONS` y `DATA_SERVICES_POINTS`)
- `test_extract_separates_polygons_and_points` (un way cerrado va a polygons, un node va a points)
- `test_extract_skips_unclassified_elements`

---

## Edge cases & error handling

| Caso | Manejo |
|---|---|
| Overpass timeout / 5xx | `query_with_retry` maneja multi-endpoint con backoff (reusado de vial). 3 reintentos. Si todos fallan, raise + mensaje claro. |
| Bucket vacío (0 prisons) | OK — dict tiene `[]` para esa categoría. Frontend itera sin error. |
| Way con <3 nodos | `infer_geometry_kind` devuelve "point". Se rendea como marker en primer nodo. Log warning. |
| Polígono gigante (Theodore Wirth Park ~3km²) | Leaflet Canvas lo maneja bien (vial rendea 108k features). |
| Element sin tag `name` en categoría no-restringida (e.g., school) | Se incluye con `name: None` → popup muestra "(sin nombre)" |
| Element con múltiples tags clasificables | `classify_service` devuelve la PRIMERA categoría matched (determinístico Python 3.7+) |
| XSS en popup | TODO el contenido pasa por `escHtml` — patrón existente del módulo zoning. NO escribimos nueva función. |
| `datos_servicios.js` no existe | `onerror` setea `window.__noServicesPrebuilt=true`; `renderServicesFeatures()` chequea y warneja en console sin romper visualizer |

---

## Verificación visual manual (end-of-session)

Después de implementar:
1. Correr `uv run extract-services` con bbox real
2. Abrir `start-visualizer.bat`
3. Validar:
   - ✅ Las 5 capas aparecen en Layer Control sección "Servicios"
   - ✅ Hennepin Healthcare aparece como polígono `#D81B60`
   - ✅ U of M campus aparece como polígono `#FDD835`
   - ✅ Minnehaha Park aparece como polígono `#43A047`
   - ✅ Walker Art Center aparece como polígono `#1E88E5` (museo en bucket admin)
   - ✅ Markers H/E/B/A/P aparecen en zoom ≥ 12 y desaparecen en zoom < 12
   - ✅ Click en marker → popup con name + subtype + tags colapsables
   - ✅ Toggles del Layer Control ocultan/muestran capas correctamente

---

## Scope diferido a Sesión 4

Las **3 capas de infraestructura** que requieren fuentes no-OSM:

| Capa CS2 | Fuente principal | Por qué no en Sesión 3 |
|---|---|---|
| Electricidad | EIA (US Energy Info Admin) + power=* de OSM como complemento | OSM tiene cobertura ~30-50% para subestaciones, casi nada para distribución |
| Agua y saneamiento | MN GIS Commons + opendata.minneapolismn.gov | OSM tiene asset grandes pero faltan tuberías y detalle municipal |
| Gestión de residuos | opendata.minneapolismn.gov | OSM tiene <20 features útiles en Minneapolis |

**Trabajo adicional requerido:**
- `src/services/sources/` con cliente por fuente (no solo `overpass_client`)
- Reproyección con `pyproj` (nueva dependencia) — MN State Plane → WGS84
- Reconciliación de duplicados OSM↔EIA cuando hay overlap
- Probablemente +1 sesión completa de trabajo

**Crear al cierre de Sesión 3:**
- `📦 Sesión 4 — Módulo Infraestructura.md` en Obsidian con este scope
- Actualizar `📋 Estado del Proyecto.md` con fila Sesión 4

---

## Out of scope explícito (follow-up backlog)

Conscientemente fuera de Sesión 3:
- Search/filter UI ("buscar Hennepin" y highlight)
- Export a GeoJSON / KML
- Iconos SVG custom (estamos con char en círculo — funciona, no requiere assets nuevos)
- Cluster de markers (no esperamos densidades >50/bucket en zoom alto)
- Filtro por subtype dentro del Layer Control (solo "hospitales" o solo "clínicas")

---

## Predecesor y contexto

- [Sesión 1 — Módulo Zonificación](./2026-05-13-cs2-zone-realignment.md) — 13 zonas CS2, paleta verde/azul/morado/amarillo/teal
- [Sesión 2 — Módulo Red Vial](./2026-05-15-modulo-vial.md) — 108k features, 6 categorías, paleta rojo/naranja/marrón/gris/cian/verde
- [Sesión 2.5 — Toolkit Reorg v3.1](../specs/2026-05-15-toolkit-reorg-design.md) — sub-paquetes `src/shared/`, `src/vial/`, `src/zoning/`

**Repo:** https://github.com/Osyanne/cs2-minneapolis-osm-toolkit (v3.1 publicado, prebuilts en GitHub Releases)
