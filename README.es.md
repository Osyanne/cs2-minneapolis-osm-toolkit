# CS2 Minneapolis OSM Toolkit — v3.3

> Datos GIS reales de OpenStreetMap → Cities: Skylines 2
> Toolkit modular · 100% open source · Sin API keys · Mapa interactivo dark

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)
![License MIT](https://img.shields.io/badge/License-MIT-green)
![OSM Data](https://img.shields.io/badge/Data-OpenStreetMap-orange)
![Tests](https://img.shields.io/badge/tests-171%20passing-success)

> 🇬🇧 English version: [README.md](README.md)

---

## Ciudades destacadas (v3.3)

El toolkit ahora soporta **4 ciudades** out-of-the-box, accesibles vía el visualizer hosteado en:

**https://osyanne.github.io/CitiesSkylines2-osm-toolkit/**

| Ciudad | País | Módulos |
|--------|------|---------|
| Minneapolis, MN | USA | Zoning + Vial + Servicios (hero, fully featured) |
| Amsterdam | Netherlands | Zoning |
| Madison, WI | USA | Zoning |
| Charleston, SC | USA | Zoning |

Vial + servicios para las 3 ciudades nuevas son **on-demand**: abrí un [City Request issue](https://github.com/Osyanne/CitiesSkylines2-osm-toolkit/issues/new?template=city-request.yml) pidiéndolas, y las generamos.

### Agregá tu ciudad

Abrí un [City Request issue](https://github.com/Osyanne/CitiesSkylines2-osm-toolkit/issues/new?template=city-request.yml) con el bbox + nombre. Generamos el prebuilt de zoning y publicamos (~30-60 min de turnaround si está activo).

### Rename del repo — pendiente

Este repo se va a renombrar a `cs2-osm-toolkit` para reflejar el soporte multi-city. El rename está diferido hasta que el tráfico actual de Reddit decaiga. Los links y clones existentes siguen funcionando vía redirects de GitHub.

---

## Inicio rápido — Elige tu camino

### Opción A: Solo ver los mapas

Dos opciones:

**Opción 1 — Hosteado (sin setup, sin instalar nada):** Visitá https://osyanne.github.io/CitiesSkylines2-osm-toolkit/ en tu browser. Hacé clic en cualquiera de las 5 tarjetas de ciudad para abrir el mapa.

**Opción 2 — Clonar localmente (necesitás un mini HTTP server):** Cloná el repo, después serví el folder `visualizer/` por HTTP:

```bash
cd cs2-osm-toolkit/visualizer
python -m http.server 8000
```

Abrí `http://localhost:8000/` en tu browser. Los datos de las 4 ciudades están incluidos en el repo — no hace falta descargar nada extra.

> **¿Por qué HTTP y no doble clic?** El visualizer usa `fetch()` para leer el registro de ciudades y el manifest de cada ciudad. Los browsers bloquean `fetch()` desde URLs `file://` por defecto (política CORS), entonces abrir `index.html` con doble clic muestra el landing pero los mapas de cada ciudad fallan. Cualquier mini HTTP server funciona — el built-in de Python (arriba), `http-server` de Node, o la extensión Live Server de VS Code.

### Opción B: Usarlo para tu ciudad (15–20 minutos, requiere Python)

Guía paso a paso completa: [docs/QUICKSTART.md](docs/QUICKSTART.md).

La versión corta:
1. Instalá Python 3.11+ con la casilla "Add to PATH" marcada, luego instalá uv
2. Abrí una terminal en la carpeta `src/` y ejecutá `uv sync`
3. Agregá tu ciudad en `cities.json` en la raíz del repo con el bbox, y ejecutá:

        uv run extract-zoning --city your_slug
        uv run extract-vial --city your_slug      (opcional)
        uv run extract-services --city your_slug  (opcional)

4. Ejecutá `uv run generate-landing` para actualizar la landing

Para extracts puntuales sin modificar `cities.json`, usá el escape hatch: `uv run extract-zoning --bbox "sur,oeste,norte,este" --slug your_slug` (ambos flags se requieren juntos).

**¿Algo no funciona?** Ver [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

### Opción C: Desarrollar o contribuir

Clona el repo, ejecuta `uv sync` dentro de `src/`, corre los tests con `uv run pytest`. Todos los detalles técnicos abajo.

---

## ¿Qué hace este toolkit?

Un toolkit modular que extrae datos reales de infraestructura desde OpenStreetMap (vía Overpass API) y los renderiza en un mapa Leaflet dark-mode interactivo. Sirve como referencia visual para construir Mineapolis 1:1 en Cities: Skylines 2. Tres módulos, ~192k features en total.

### 🗺 Módulo Zonificación
Clasifica todos los polígonos de edificios en los **11 tipos de zona oficiales de Cities: Skylines 2** (Low/Medium/High Density Residential, Row Housing, Mixed Housing, Low Rent Housing, Low/High Density Business, Low/High Density Offices, Industrial Manufacturing). 81.732 polígonos en el bbox de Mineapolis.

Ejecutar: `cd src && uv run extract-zoning --city minneapolis`
Salida: `visualizer/cities/minneapolis/datos_zonificacion.js` (~28 MB)

### 🛣 Módulo Red Vial
Clasifica todas las vías OSM en las **6 categorías de carretera de CS2** (Highway, Major Road, Minor Road, Local Street, Pedestrian Path, Bike Lane). Se renderiza como capa de LineStrings. 108.825 features.

Ejecutar: `cd src && uv run extract-vial --city minneapolis`
Salida: `visualizer/cities/minneapolis/datos_vial.js` (~25 MB)

### 🏥 Módulo Servicios
5 capas alineadas a las solapas de servicios base de Cities: Skylines 2 con buena cobertura OpenStreetMap:

- **H** Atención sanitaria y funeraria — hospitales, clínicas, doctors, funeral directors, crematorios, cementerios
- **E** Educación e investigación — schools, universities, colleges, kindergartens, research institutes
- **B** Bomberos — fire stations
- **A** Policía y administración — police HQ, city hall, courthouses, prison + landmarks culturales (bibliotecas, museos, teatros, arts centres, cinemas) + oficinas de gobierno
- **P** Parques — parks, nature reserves, gardens, playgrounds, sports centres

Ejecutar: `cd src && uv run extract-services --city minneapolis`
Salida: `visualizer/cities/minneapolis/datos_servicios.js` (~1,3 MB)

**Notas:**
- Bibliotecas, museos, teatros, arts centres, cinemas comparten el bucket `admin` con policía y oficinas de gobierno. Se diferencian solo por nombre + subtype en el popup.
- Lugares de culto descartados conscientemente (no en estructura CS2 base).
- Electricidad, agua y saneamiento, gestión de residuos diferidos a Sesión 4 (requieren fuentes EIA + MN GIS Commons + opendata.minneapolismn.gov, no OSM).
- Bbox de Minneapolis típicamente devuelve ~2.300 features. Render async chunked para no bloquear el browser.

### Próximos
- 🚌 Módulo Transporte (Blue/Green Line, BRT, rutas de bus, ciclovías) — Sesión 4

---

## Features del visualizer

- **Module pills (arriba derecha)**: toggle módulos enteros en un click
- **Master toggles en leyenda**: mismo efecto, espejado en la barra lateral
- **Modo de fondo** (cuando hay módulos apagados): Oculto / Atenuado / Completo
- **Layer Control** (arriba derecha): toggle granular por zona / categoría vial
- **Canvas renderer**: pan/zoom fluido con 80k+ polígonos + 108k linestrings
- **Tier-based hiding**: casas individuales se ocultan en zoom <14, bloques siempre visibles
- **Paleta fiel a CS2**: 4 familias (verde/azul/morado/amarillo) alineadas al HUD del juego
- **Tema oscuro**: basemap CartoDB Dark Matter
- **Persistencia**: estado de la vista guardado en localStorage (`cs2-view-state-{slug}-v1`, con scope por ciudad)

---

## Setup técnico

### Requisitos
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (reemplazo más rápido de pip+venv)

### Setup

```bash
git clone https://github.com/Osyanne/CitiesSkylines2-osm-toolkit.git
cd cs2-osm-toolkit/src
uv sync
```

### Prebuilts (ya están en el repo)

Los archivos prebuilt `datos_*.js` de las 4 ciudades están **commiteados en `visualizer/cities/<slug>/`**. No hace falta descargar nada.

**Para regenerar datos frescos** (ej., tras actualizaciones de OSM):

```bash
cd src
uv run extract-zoning --city minneapolis    # ~3-5 min
uv run extract-vial --city minneapolis      # ~30s
uv run extract-services --city minneapolis  # ~1 min
```

Reemplazá `minneapolis` con cualquier slug del registro `cities.json` (`manhattan`, `tokyo`, `amsterdam`, `madison`). Cada extracción actualiza el manifest preservando los otros módulos.

### Levantar el visualizer

```bash
cd visualizer
python -m http.server 8000
# Abrir http://localhost:8000/ (landing) o http://localhost:8000/map.html?city=minneapolis (mapa directo)
```

### Correr tests

```bash
cd src
uv run pytest
```

171 tests pasando en módulos de zoning, vial y services.

---

## Estructura del proyecto

```
cities.json                   # Registro multi-ciudad (bbox, center, zoom, metadata)

src/
├── shared/
│   ├── overpass_client.py    # Cliente Overpass con retry + rotación de endpoints
│   ├── registry.py           # Lee cities.json; resuelve --city <slug> a bbox
│   └── landing.py            # CLI generate-landing (reconstruye visualizer/index.html)
├── zoning/
│   ├── zones.py              # Modelo de zonas CS2 + queries Overpass
│   ├── classifiers.py        # Clasificador OSM tag → zona CS2
│   ├── extract.py            # Pipeline CLI (entry: extract-zoning)
│   └── patch_colors.py       # Utility de paleta
├── vial/
│   ├── zones.py              # Modelo de vías CS2 + query Overpass
│   ├── classifiers.py        # Clasificador OSM highway tag → categoría vial
│   └── extract.py            # Pipeline CLI (entry: extract-vial)
└── services/
    ├── zones.py              # Modelo de servicios CS2 + queries Overpass (5 buckets)
    ├── classifiers.py        # Clasificador OSM tags → bucket H/E/B/A/P
    └── extract.py            # Pipeline CLI (entry: extract-services)

tests/
├── zoning/                   # 84 tests
├── vial/                     # 33 tests
└── services/                 # 54 tests
                              # 171 en total

visualizer/
├── index.html                # Landing — galería de 5 tarjetas de ciudad
├── map.html                  # Visor de mapa — se carga como map.html?city=<slug>
├── cities.json               # Artefacto de deployment (copia del cities.json raíz)
├── cities/
│   ├── minneapolis/          # datos_zonificacion.js + datos_vial.js + datos_servicios.js + manifest.json
│   ├── manhattan/            # datos_zonificacion.js + manifest.json
│   ├── tokyo/                # datos_zonificacion.js + manifest.json
│   ├── amsterdam/            # datos_zonificacion.js + manifest.json
│   └── madison/              # datos_zonificacion.js + manifest.json
└── assets/
    └── thumbnails/           # minneapolis.png, manhattan.png, tokyo.png, amsterdam.png, madison.png

docs/
├── QUICKSTART.md             # Guía ELI5 para usuarios no técnicos
├── TROUBLESHOOTING.md        # Errores comunes y soluciones
├── adapting-to-other-cities.md
├── bbox-mcp-server.md
├── cs2-zone-reference.md
├── github-publishing.md
├── plans/                    # Planes de implementación por sesión
└── specs/                    # Specs de diseño

.github/
└── ISSUE_TEMPLATE/
    └── city-request.yml      # Template de issue para solicitar ciudad
```

---

## Stats del proyecto

| | |
|---|---|
| **Módulos** | 3 módulos × 4 ciudades (Mpls completo + 3 solo zoning) — Transporte pendiente |
| **Bounding box** | 4 ciudades, ver `cities.json` |
| **Features totales** | ~332k (Mpls 192k + Amsterdam 89k + Madison 37k + Charleston 14.5k) |
| **Tests** | 171 pasando |
| **Última extracción** | 2026-05-17 |

---

## Adaptarlo a otras ciudades

El pipeline es multi-ciudad mediante el registro `cities.json` en la raíz del repo. Para agregar una ciudad:

1. Agregá una entrada en `cities.json` con `display_name`, `country`, `bbox`, `center`, `zoom`, `tagline`, `locale`
2. Ejecutá `uv run extract-zoning --city <your_slug>` (y opcionalmente `extract-vial` / `extract-services`)
3. Ejecutá `uv run generate-landing` para actualizar la landing
4. Abrí un PR al repo upstream si querés que quede incluida para todos

Para extracts puntuales sin modificar `cities.json`: `uv run extract-zoning --bbox "s,o,n,e" --slug your_city`.

Ver [docs/adapting-to-other-cities.md](docs/adapting-to-other-cities.md) para guía específica por ciudad, ejemplos de bbox y calibración de umbrales de densidad.

---

## Licencia

MIT. Datos OSM via OpenStreetMap contributors bajo ODbL.
