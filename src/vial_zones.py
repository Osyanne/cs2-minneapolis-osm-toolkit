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
    cycleway} (incluyendo variantes _link para motorway/trunk/primary/
    secondary/tertiary), con geometría.
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
