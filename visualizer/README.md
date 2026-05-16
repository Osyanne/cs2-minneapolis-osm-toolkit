# CS2 Minneapolis OSM — Visualizer

Visualizador interactivo Leaflet del mapa de Minneapolis con overlays de zonificación y red vial.

## Quick start

```bash
# Servir el visualizer en localhost:8080
cd visualizer
python -m http.server 8080
```

Abrir en navegador: **http://localhost:8080/index.html**

## Obtener prebuilts (datos pre-generados)

Los archivos `datos_zonificacion.js` (~28 MB) y `datos_vial.js` (~25 MB) NO están commiteados en el repo (son binarios grandes). Tienes dos opciones:

### Opción A: Descargar desde GitHub Releases (recomendado)

1. Ir a https://github.com/Osyanne/cs2-minneapolis-osm-toolkit/releases
2. Descargar `datos_zonificacion.js` y `datos_vial.js` desde la última release
3. Colocarlos en este directorio (`visualizer/`)

### Opción B: Regenerar localmente

```bash
cd ../src
uv run extract-zoning    # ~3-5 min  → ../visualizer/datos_zonificacion.js
uv run extract-vial      # ~30s      → ../visualizer/datos_vial.js
```

Los archivos se escriben directamente a `visualizer/`.

## Modo sin prebuilts

Si abres el visualizer sin los prebuilts, el código JavaScript detecta la ausencia automáticamente y:

- **Zonificación**: cae a modo live Overpass (descarga las 9 queries en paralelo, tarda ~2-3 min la primera vez, se cachea 24h en localStorage)
- **Red Vial**: simplemente no se renderea — el visualizer funciona pero solo con el módulo zoning

## Controles de UI

- **Module pills (arriba derecha)**: toggle ON/OFF de cada módulo entero (Zoning / Vial / Servicios / Transporte)
- **Master toggle en leyenda** (●): espejo de las pills, mismo efecto
- **Control "Fondo"** (aparece si hay módulos en OFF): Oculto / Atenuado / Completo
- **Layer Control** (esquina arriba derecha): toggle granular por zona / categoría vial individual

## Persistencia

El estado de las pills + el modo de fondo se guarda en `localStorage` (clave `cs2-mineapolis-view-state-v1`). La próxima vez que abras el visualizer recuerda tu última vista.

Para reset: abre DevTools → Application → Local Storage → borrar la clave.
