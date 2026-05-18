# CS2 OSM Toolkit — Visualizer (v3.3)

Visualizador interactivo Leaflet **multi-city** del toolkit OSM para Cities: Skylines 2. Soporta 5 ciudades curadas: Minneapolis (zoning + vial + services) y Manhattan / Tokyo / Amsterdam / Madison (zoning only).

## Quick start

```bash
# Servir el visualizer en localhost:8000
cd visualizer
python -m http.server 8000
```

Dos puntos de entrada:

- **Landing con galería** — http://localhost:8000/index.html — muestra las 5 ciudades disponibles, click en card para abrir el mapa
- **Mapa directo de una ciudad** — http://localhost:8000/map.html?city=minneapolis (también `manhattan`, `tokyo`, `amsterdam`, `madison`)

Si abrís `map.html` sin `?city=`, redirige a la landing automáticamente. Slug inválido también redirige.

## Prebuilts

Los archivos de datos (`datos_zonificacion.js`, `datos_vial.js`, `datos_servicios.js`) **ya están commiteados** en el repo bajo `visualizer/cities/<slug>/`. **No hay que descargar nada.**

Estructura:

```
visualizer/cities/
├── minneapolis/    # full: zoning + vial + services
├── manhattan/      # zoning only
├── tokyo/          # zoning only
├── amsterdam/      # zoning only
└── madison/        # zoning only
```

Cada directorio incluye un `manifest.json` que declara qué módulos están presentes + sus hashes sha256 para cache busting. El visualizer lo lee primero y solo inyecta scripts para los módulos disponibles — por eso las 4 ciudades nuevas no muestran controles de Vial ni Servicios en la leyenda.

### Regenerar datos localmente (opcional)

Si querés re-extraer datos frescos desde OpenStreetMap:

```bash
cd ../src
uv run extract-zoning   --city minneapolis    # ~3-5 min  → cities/minneapolis/datos_zonificacion.js
uv run extract-vial     --city minneapolis    # ~30s      → cities/minneapolis/datos_vial.js
uv run extract-services --city minneapolis    # ~1 min    → cities/minneapolis/datos_servicios.js
```

Reemplazá `minneapolis` con cualquier slug del registro (`cities.json`). Cada extract actualiza el `manifest.json` correspondiente preservando los módulos ya generados (podés agregar vial a Manhattan sin perder su zoning).

Para ciudades fuera del registro: `uv run extract-zoning --bbox "s,w,n,e" --slug mi_ciudad` (escape hatch sin tocar `cities.json`).

### Regenerar landing

Si agregás o modificás ciudades:

```bash
cd ../src
uv run generate-landing    # regenera visualizer/index.html + copia cities.json
```

## Controles de UI

- **Module pills (arriba derecha)** — toggle ON/OFF de cada módulo presente (Zoning / Vial / Servicios). Solo aparecen los módulos que tiene esa ciudad
- **Master toggle en leyenda** (●) — espejo de las pills, mismo efecto
- **Control "Fondo"** (aparece si hay módulos en OFF) — Oculto / Atenuado / Completo
- **Layer Control** (esquina arriba derecha) — toggle granular por zona / categoría vial individual

## Persistencia

El estado de las pills + el modo de fondo se guarda en `localStorage` con clave **scoped por ciudad**: `cs2-view-state-{slug}-v1` (ej. `cs2-view-state-minneapolis-v1`). Cada ciudad recuerda independientemente su última vista — cambiar de Manhattan a Tokyo no pisa la configuración de la otra.

Para reset de una ciudad: DevTools → Application → Local Storage → borrar la clave correspondiente.

## ¿Tu ciudad no está?

Abrí un [City Request issue](https://github.com/Osyanne/cs2-minneapolis-osm-toolkit/issues/new?template=city-request.yml) con el bbox + nombre. Generamos el prebuilt de zoning y publicamos (~30-60 min turnaround si está activo). Vial + services son ampliación on-demand si la ciudad acumula múltiples requests.
