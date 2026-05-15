"""
vial_classifiers.py — Clasificador de tags highway → categoría CS2 (Sesión 2)
=============================================================================
Mapeo puro tabla → categoría. Sin heurísticas, sin geometría: el tag
highway=* es suficiente para decidir la categoría CS2.

  motorway, motorway_link, trunk, trunk_link        → highway
  primary, primary_link, secondary, secondary_link  → major
  tertiary, tertiary_link, residential, unclassif.  → minor
  living_street, service                            → local
  pedestrian, footway, path, steps                  → pedestrian
  cycleway                                          → bike
  otros / ausente                                   → None (omitir)
"""

_HIGHWAY_TO_CS2 = {
    # highway
    "motorway":       "highway",
    "motorway_link":  "highway",
    "trunk":          "highway",
    "trunk_link":     "highway",
    # major
    "primary":        "major",
    "primary_link":   "major",
    "secondary":      "major",
    "secondary_link": "major",
    # minor
    "tertiary":       "minor",
    "tertiary_link":  "minor",
    "residential":    "minor",
    "unclassified":   "minor",
    # local
    "living_street":  "local",
    "service":        "local",
    # pedestrian
    "pedestrian":     "pedestrian",
    "footway":        "pedestrian",
    "path":           "pedestrian",
    "steps":          "pedestrian",
    # bike
    "cycleway":       "bike",
}


def classify_highway(tags: dict) -> str | None:
    """
    Devuelve la categoría CS2 ('highway' | 'major' | 'minor' | 'local' |
    'pedestrian' | 'bike') o None si el tag highway falta o no es soportado.
    """
    hw = (tags.get("highway") or "").lower()
    return _HIGHWAY_TO_CS2.get(hw)
