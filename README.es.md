# CS2 Minneapolis Zoning — Herramienta GIS de Extracción v3.0

> Zonificación real de OpenStreetMap → Cities: Skylines 2
> 100% open source · Sin API keys · Mapa interactivo dark · 81,000+ polígonos

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)
![License MIT](https://img.shields.io/badge/License-MIT-green)
![OSM Data](https://img.shields.io/badge/Data-OpenStreetMap-orange)
![Tests](https://img.shields.io/badge/tests-72%20passing-success)

> 🇬🇧 English version: [README.md](README.md)

## Preview

![Mineapolis completa a zoom 12](docs/screenshots/preview_full.png)
*Vista completa de Mineapolis a zoom 12 — silueta de la ciudad con todas las familias de zonas*

![Downtown a zoom 15](docs/screenshots/preview_downtown.png)
*Downtown a zoom 15 — alta densidad comercial (azul), oficinas (morado), río Mississippi*

![Uptown a zoom 15](docs/screenshots/preview_uptown.png)
*Uptown / Bde Maka Ska a zoom 15 — grid residencial con corredores comerciales*

## Qué hace

Extrae polígonos de zonificación reales desde OpenStreetMap (via Overpass API), los clasifica en **los 11 tipos de zona oficiales de Cities: Skylines 2** y los renderiza en un mapa interactivo dark-mode que puedes usar como referencia mientras construyes tu ciudad CS2.

```
OpenStreetMap (Overpass API)
        ↓
  extract_zoning.py          ← 7 queries source, multi-endpoint con retry, spatial joins
        ↓
  datos_zonificacion.js      ← Polígonos clasificados por tipo de zona CS2
        ↓
  visualizer/index.html      ← Mapa Leaflet.js (Canvas renderer para 80k+ polys)
```

Sin API keys. Sin servicios pagados. Sin PostGIS. Solo Python + un archivo HTML.

## Mapeo de zonas CS2

Las **11 zonas oficiales de CS2** + parking (referencia visual):

**Residencial (verde, 6):**
- Low Density Housing, Medium Density Row Housing, Medium Density Housing, **Mixed Housing** (teal), Low Rent Housing, High Density Housing

**Comercial (azul, 2):** Low Density Business, High Density Business

**Oficinas (morado, 2):** Low Density Offices, High Density Offices

**Industrial (amarillo, 1):** Industrial Manufacturing

**Parking (gris, no es zona CS2):** Surface Parking, Parking Structure

La tabla detallada de reglas OSM → CS2 está en [README.md](README.md#cs2-zone-mapping).

## Inicio rápido

```bash
# 1. Clonar
git clone https://github.com/Osyanne/cs2-minneapolis-zoning
cd cs2-minneapolis-zoning

# 2. Instalar uv (si no está instalado)
# Windows: powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 3. Instalar dependencias
cd src
uv sync

# 4. Extraer datos (~3-5 min, descarga de OpenStreetMap)
uv run extract_zoning.py

# 5. Abrir el visualizador
cd ../visualizer
python -m http.server 8080
# → abre http://localhost:8080 en tu navegador
```

**Windows:** doble-click en `start-visualizer.bat` para arrancar todo automáticamente.

## Adaptar a tu ciudad

Edita `MINNEAPOLIS_BBOX` en `src/cs2_zones.py` o pasa `--bbox "sur,oeste,norte,este"` al script:

```bash
uv run extract_zoning.py --bbox "40.70,-74.02,40.83,-73.91"  # NYC ejemplo
```

Ver [docs/adapting-to-other-cities.md](docs/adapting-to-other-cities.md) para guía detallada.

## Optimizaciones de rendimiento (v3.0)

| Feature | Impacto |
|---|---|
| **Canvas renderer** | Pan/zoom con 81k polígonos: laggy → fluido |
| **Tier-based hiding** | Auto-oculta casas individuales en zoom <14 |
| **localStorage cache** | Segunda carga instantánea (24h TTL) |
| **Prebuilt data mode** | Primera carga <1s vs 3-5 min de Overpass live |
| **Spatial join** | Mixed Housing: 3 → 123 polígonos detectados |
| **Multi-endpoint retry** | Resiliente a sobrecarga de Overpass |

## Evolución del proyecto

Los planes detallados están en [docs/plans/](docs/plans/):

- **Sesión 1** — clasificación de densidad, visualizador básico
- **Sesión 1.5** — 5 bugs cerrados + paleta CS Skylines + 32 tests
- **Sesión 1.6** — modelo realineado a CS2 oficial (13 zonas), heurística de footprint, paleta de 4 familias
- **Sesión 1.7** — Canvas renderer + tier-based hiding por área de polígono
- **Sesión 1.8** (experimental, revertida) — augmentación con Microsoft Buildings. El script `src/extract_msbuildings.py` queda en el repo para mejorar en el futuro. Bug conocido: clasifica mal casas suburbanas cerca de corredores comerciales.
- **Sesión 2** — Módulo Red Vial (ver abajo)

### Módulo Red Vial (Sesión 2)

Extrae la red vial de OpenStreetMap y la clasifica en 6 categorías de CS2: Highway, Major Road, Minor Road, Local Street, Pedestrian Path, Bike Lane. Se renderiza como capa de LineStrings superpuesta sobre el mapa de zonificación.

Ejecutar: `uv run extract_vial.py`
Salida: `visualizer/datos_vial.js` (~25 MB, 108.825 features en el bbox de Minneapolis).

## Metodología

Todas las decisiones de diseño documentadas en [METHODOLOGY.md](METHODOLOGY.md).

## Cobertura de datos

| | |
|---|---|
| **Bounding box** | `44.86,-93.38,45.05,-93.17` (Mineapolis + bordes inmediatos) |
| **Polígonos totales** | 81,732 |
| **Tests** | 72 pasando (50 clasificador + 11 sanidad zoning + 11 sanidad vial) |
| **Última extracción** | 2026-05-14 |

## Licencia

MIT — ver [LICENSE](LICENSE)
Datos de mapa © contribuidores OpenStreetMap bajo [Open Database License (ODbL)](https://www.openstreetmap.org/copyright)
