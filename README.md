# CS2 Minneapolis OSM Toolkit — v3.3

> Real-world GIS data from OpenStreetMap → Cities: Skylines 2
> Modular toolkit · 100% open source · Zero API keys · Interactive dark map

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)
![License MIT](https://img.shields.io/badge/License-MIT-green)
![OSM Data](https://img.shields.io/badge/Data-OpenStreetMap-orange)
![Tests](https://img.shields.io/badge/tests-171%20passing-success)

> 🇪🇸 Versión en español: [README.es.md](README.es.md)

---

## Featured Cities (v3.3)

The toolkit now supports **6 cities** out-of-the-box, accessible via the hosted viewer at:

**https://osyanne.github.io/CitiesSkylines2-osm-toolkit/**

| City | Country | Modules |
|------|---------|---------|
| Minneapolis, MN | USA | Zoning + Vial + Services (hero, fully featured) |
| Amsterdam | Netherlands | Zoning |
| Madison, WI | USA | Zoning |
| Charleston, SC | USA | Zoning |
| Trondheim | Norway | Zoning |
| Mafra, SC | Brazil | Zoning |

Vial + services for non-hero cities are temporarily paused for new requests while we focus on broadening zoning coverage. Existing modules stay live.

### Adding your city

Open a [City Request issue](https://github.com/Osyanne/CitiesSkylines2-osm-toolkit/issues/new?template=city-request.yml) with the bbox + name. We'll generate the zoning prebuilt and publish (~30-60 min turnaround when active).

### Repo rename — pending

This repo will eventually be renamed `cs2-osm-toolkit` to reflect multi-city support. Rename is deferred until current Reddit traffic decays. Existing links and clones continue to work via GitHub redirects.

---

## Quick Start — Pick Your Path

### Path A: Just look at the maps

Two options:

**Option 1 — Hosted (zero setup, no install):** Visit https://osyanne.github.io/CitiesSkylines2-osm-toolkit/ in your browser. Click any of the 5 city cards to open the map.

**Option 2 — Local clone (need any tiny HTTP server):** Clone the repo, then serve the `visualizer/` folder over HTTP:

```bash
cd cs2-osm-toolkit/visualizer
python -m http.server 8000
```

Open `http://localhost:8000/` in your browser. All 6 cities' data is included in the repo — no extra downloads needed.

> **Why HTTP and not just double-click?** The map viewer uses `fetch()` to load the city registry and per-city manifest. Browsers block `fetch()` from `file://` URLs by default (CORS policy), so opening `index.html` directly with double-click shows the landing but city maps fail to load. Any tiny HTTP server works — Python's built-in (above), Node's `http-server`, or VS Code's Live Server extension.

### Path B: Use it for your city (15–20 minutes, requires Python)

Full step-by-step walkthrough: [docs/QUICKSTART.md](docs/QUICKSTART.md).

The short version:
1. Install Python 3.11+ with "Add to PATH" checked, then install uv
2. Open a terminal in the `src/` folder and run `uv sync`
3. Add your city to `cities.json` at repo root with bbox, then run:

        uv run extract-zoning --city your_slug
        uv run extract-vial --city your_slug      (optional)
        uv run extract-services --city your_slug  (optional)

4. Run `uv run generate-landing` to update the landing page

For ad-hoc one-off extracts without modifying `cities.json`, use the escape hatch: `uv run extract-zoning --bbox "south,west,north,east" --slug your_slug` (both flags required together).

**Common issues?** See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

### Path C: Develop or contribute

Clone the repo, run `uv sync` inside `src/`, run tests with `uv run pytest`. All technical details below.

---

## What This Does

A modular toolkit that extracts real-world infrastructure data from OpenStreetMap via the Overpass API and renders it on an interactive dark-mode Leaflet map. Built as a reference layer for players recreating Minneapolis 1:1 in Cities: Skylines 2. Three modules, ~192k total features.

### 🗺 Zoning Module
Classifies all building polygons into the **11 official Cities: Skylines 2 zone types** (Low/Medium/High Density Residential, Row Housing, Mixed Housing, Low Rent Housing, Low/High Density Business, Low/High Density Offices, Industrial Manufacturing). 81,732 polygons in the Minneapolis bbox.

Run: `cd src && uv run extract-zoning --city minneapolis`
Output: `visualizer/cities/minneapolis/datos_zonificacion.js` (~28 MB)

### 🛣 Road Network Module
Classifies all OSM roads into the **6 CS2 road categories** (Highway, Major Road, Minor Road, Local Street, Pedestrian Path, Bike Lane). Renders as LineString overlay. 108,825 features.

Run: `cd src && uv run extract-vial --city minneapolis`
Output: `visualizer/cities/minneapolis/datos_vial.js` (~25 MB)

### 🏥 Services Module
5 layers aligned to the base service tabs of Cities: Skylines 2 with good OpenStreetMap coverage:

- **H** Healthcare & Deathcare — hospitals, clinics, doctors, funeral directors, crematoriums, cemeteries
- **E** Education & Research — schools, universities, colleges, kindergartens, research institutes
- **B** Fire — fire stations
- **A** Police & Administration — police HQ, city hall, courthouses, prison + cultural landmarks (libraries, museums, theatres, arts centres, cinemas) + government offices
- **P** Parks — parks, nature reserves, gardens, playgrounds, sports centres

Run: `cd src && uv run extract-services --city minneapolis`
Output: `visualizer/cities/minneapolis/datos_servicios.js` (~1.3 MB)

**Notes:**
- Libraries, museums, theatres, arts centres, cinemas share the `admin` bucket with police and government offices. They differ only by name + subtype in the popup.
- Places of worship intentionally excluded (not in CS2 base game structure).
- Electricity, water & sewage, waste management deferred to Session 4 (require EIA + MN GIS Commons + opendata.minneapolismn.gov sources, not OSM).
- Minneapolis bbox typically returns ~2,300 features. Async chunked rendering prevents browser blocking during init.

### Coming next
- 🚌 Transit Module (Blue/Green Line, BRT, bus routes, bikeways) — Session 4

---

## Visualizer Features

- **Module pills (top right)**: toggle entire modules on/off in one click
- **Master toggles in legend**: same effect, mirrored in the sidebar
- **Background mode** (when modules are off): Hidden / Faded / Full
- **Layer Control** (top right): granular per-zone / per-road-category toggles
- **Canvas renderer**: smooth pan/zoom with 80k+ polygons + 108k linestrings
- **Tier-based hiding**: individual houses hide at zoom <14, blocks stay visible
- **CS2-faithful color palette**: 4 families (green/blue/purple/yellow) aligned to the game HUD
- **Dark theme**: CartoDB Dark Matter basemap
- **Persistence**: view state saved to localStorage (`cs2-view-state-{slug}-v1`, scoped per city)

---

## Technical Setup

### Prerequisites
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (faster pip+venv replacement)

### Setup

```bash
git clone https://github.com/Osyanne/CitiesSkylines2-osm-toolkit.git
cd cs2-osm-toolkit/src
uv sync
```

### Prebuilts (already in the repo)

The prebuilt `datos_*.js` files for all 6 cities are **committed in `visualizer/cities/<slug>/`**. No download needed.

**To regenerate fresh data** (e.g., after OSM updates):

```bash
cd src
uv run extract-zoning --city minneapolis    # ~3-5 min
uv run extract-vial --city minneapolis      # ~30s
uv run extract-services --city minneapolis  # ~1 min
```

Replace `minneapolis` with any slug from `cities.json` (`manhattan`, `tokyo`, `amsterdam`, `madison`). Each extract updates the manifest preserving other modules.

### Serve the visualizer

```bash
cd visualizer
python -m http.server 8000
# Open http://localhost:8000/ (landing) or http://localhost:8000/map.html?city=minneapolis (direct map)
```

### Run tests

```bash
cd src
uv run pytest
```

171 tests passing across zoning, vial, and services modules.

---

## Project Structure

```
cities.json                   # Multi-city registry (bbox, center, zoom, metadata)

src/
├── shared/
│   ├── overpass_client.py    # Overpass API client with retry + endpoint rotation
│   ├── registry.py           # Reads cities.json; resolves --city <slug> to bbox
│   └── landing.py            # generate-landing CLI (rebuilds visualizer/index.html)
├── zoning/
│   ├── zones.py              # CS2 zone model + Overpass queries
│   ├── classifiers.py        # OSM tag → CS2 zone classifier
│   ├── extract.py            # CLI pipeline (entry: extract-zoning)
│   └── patch_colors.py       # Color palette utility
├── vial/
│   ├── zones.py              # CS2 road model + Overpass query
│   ├── classifiers.py        # OSM highway tag → CS2 road category
│   └── extract.py            # CLI pipeline (entry: extract-vial)
└── services/
    ├── zones.py              # CS2 service model + Overpass queries (5 buckets)
    ├── classifiers.py        # OSM tags → H/E/B/A/P bucket classifier
    └── extract.py            # CLI pipeline (entry: extract-services)

tests/
├── zoning/                   # 84 tests
├── vial/                     # 33 tests
└── services/                 # 54 tests
                              # 171 total

visualizer/
├── index.html                # Landing page — gallery of 5 city cards
├── map.html                  # Map viewer — loaded as map.html?city=<slug>
├── cities.json               # Deployment artifact (copy of root cities.json)
├── cities/
│   ├── minneapolis/          # datos_zonificacion.js + datos_vial.js + datos_servicios.js + manifest.json
│   ├── manhattan/            # datos_zonificacion.js + manifest.json
│   ├── tokyo/                # datos_zonificacion.js + manifest.json
│   ├── amsterdam/            # datos_zonificacion.js + manifest.json
│   └── madison/              # datos_zonificacion.js + manifest.json
└── assets/
    └── thumbnails/           # minneapolis.png, manhattan.png, tokyo.png, amsterdam.png, madison.png

docs/
├── QUICKSTART.md             # ELI5 guide for non-technical users
├── TROUBLESHOOTING.md        # Common errors and fixes
├── adapting-to-other-cities.md
├── bbox-mcp-server.md
├── cs2-zone-reference.md
├── github-publishing.md
├── plans/                    # Session implementation plans
└── specs/                    # Design specs

.github/
└── ISSUE_TEMPLATE/
    └── city-request.yml      # City request issue template
```

---

## Project Stats

| | |
|---|---|
| **Modules** | 3 modules × 6 cities (Mpls full + 5 zoning-only) — Transit pending |
| **Bounding box** | 6 cities, see `cities.json` |
| **Total features** | ~372k (Mpls 192k + Amsterdam 89k + Trondheim 40k + Madison 37k + Charleston 14.5k + Mafra 105) |
| **Tests** | 171 passing |
| **Last extracted** | 2026-05-18 |

---

## Adapting to Other Cities

The pipeline is multi-city via `cities.json` registry at the repo root. To add a city:

1. Add an entry to `cities.json` with `display_name`, `country`, `bbox`, `center`, `zoom`, `tagline`, `locale`
2. Run `uv run extract-zoning --city <your_slug>` (and optionally `extract-vial` / `extract-services`)
3. Run `uv run generate-landing` to update the landing
4. Open a PR to the upstream repo if you want it included for everyone

For one-off extracts without modifying `cities.json`: `uv run extract-zoning --bbox "s,w,n,e" --slug your_city`.

See [docs/adapting-to-other-cities.md](docs/adapting-to-other-cities.md) for city-specific guidance, example bboxes, and density threshold calibration.

---

## License

MIT. OSM data via OpenStreetMap contributors under ODbL.
