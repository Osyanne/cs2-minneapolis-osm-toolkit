"""
transporte/classifiers.py — OSM route tags → CS2 transit category
==================================================================
Mapeo puro de tags route + network + name a una de 4 categorías CS2.

Reglas:
  route=light_rail              → lrt
  route=tram                    → lrt   (CS2 visualization)
  route=train | commuter_rail   → commuter
  route=bus + METRO Rapid       → brt   (detected via network or name pattern)
  route=bus (resto)             → bus
  otros / ausente               → None
"""


def classify_route(tags: dict) -> str | None:
    """Classify an OSM route relation into a CS2 transit category.

    Args:
        tags: OSM tags dict (route, network, name, etc.).

    Returns:
        "lrt" | "commuter" | "brt" | "bus" | None (skip).
    """
    route = (tags.get("route") or "").lower()
    network = tags.get("network") or ""
    name = tags.get("name") or ""

    if route in ("light_rail", "tram"):
        return "lrt"
    if route in ("train", "commuter_rail", "commuter"):
        return "commuter"
    if route == "bus":
        # BRT detection: METRO Rapid Lines have network=METRO or name like "METRO X Line".
        # Regular Metro Transit local buses use network=Metro Transit (note the space).
        if network == "METRO":
            return "brt"
        if "METRO" in name and " Line" in name:
            return "brt"
        return "bus"
    return None
