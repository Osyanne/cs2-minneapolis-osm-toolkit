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
    Construir una query Overpass QL que devuelve todos los servicios en los
    5 buckets CS2 (health, education, fire, admin, parks), incluyendo nodes
    y ways con geometría completa.

    El splitting nodes/ways y la clasificación se hacen en pipeline, no en
    la query.
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
