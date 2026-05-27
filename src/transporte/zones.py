"""
transporte/zones.py — Transit categories + Overpass query builder
=================================================================
4 categorías alineadas a CS2:
  lrt       → light_rail + tram (METRO Blue/Green Line)
  commuter  → train (Northstar)
  brt       → bus + network=METRO (METRO Rapid A/C/D/E/F)
  bus       → bus (resto, ~140 rutas locales Metro Transit)
"""

TRANSPORT_LABELS = {
    "lrt":      "LRT",
    "commuter": "Commuter Rail",
    "brt":      "BRT",
    "bus":      "Bus",
}


def build_transporte_query(bbox: str) -> str:
    """
    Build an Overpass QL query that returns all transit route relations
    intersecting the bbox, with their member ways' geometry.

    Args:
        bbox: "south,west,north,east" decimal degrees string.

    Returns:
        Overpass QL query string.
    """
    return f"""
[out:json][timeout:120];
(
  relation["route"~"^(light_rail|train|tram|bus)$"]({bbox});
);
out body geom;
""".strip()
