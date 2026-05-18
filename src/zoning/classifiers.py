"""
classifiers.py — Clasificación OSM → CS2 oficial (Sesión 1.6)
=============================================================
Cada función devuelve el SUFIJO de la clave CS2 (ej. "high", "low_house"),
no la clave completa. El caller compone la clave (ej. "res_high", "office_low").

API pública:
  - classify_apartment(tags, area_m2=None) → "high" | "mixed" | "low_rent" | "med"
  - classify_residential_subtype(tags)     → "low_house" | "row" | None
  - classify_landuse_residential(tags)     → "low_house"
  - classify_commercial(tags, area_m2=None) → "high" | "low"
  - classify_office(tags)                  → "high" | "low"
  - classify_parking(tags)                 → "ramp" | "surface"
  - polygon_area_m2(coords)                → float (m²) (helper)
"""

import math


# ── Helpers ─────────────────────────────────────────────────────────────────

def _effective_levels(tags: dict) -> int:
    """Niveles efectivos: max(building:levels, height/3)."""
    try:
        tag_levels = int(tags.get("building:levels") or tags.get("levels") or 0)
    except (ValueError, TypeError):
        tag_levels = 0
    try:
        height_m = float(tags.get("height") or 0)
    except (ValueError, TypeError):
        height_m = 0.0
    estimated_levels = round(height_m / 3) if height_m > 0 else 0
    return max(tag_levels, estimated_levels)


def polygon_area_m2(coords: list) -> float:
    """
    Área aproximada de un polígono en m² usando proyección equirectangular
    centrada en el centroide. Suficientemente precisa a escala urbana.
    coords: lista de [lat, lon].
    """
    if not coords or len(coords) < 3:
        return 0.0
    lat0 = sum(c[0] for c in coords) / len(coords)
    cos_lat0 = math.cos(math.radians(lat0))
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * cos_lat0
    pts = [(c[1] * m_per_deg_lon, c[0] * m_per_deg_lat) for c in coords]
    n = len(pts)
    s = 0.0
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return abs(s) / 2.0


def _is_apartment_mixed(tags: dict) -> bool:
    """¿Un edificio de apartamentos tiene comercio en la misma vía OSM?"""
    if tags.get("shop"):
        return True
    amenity = (tags.get("amenity") or "").lower()
    if amenity in ("restaurant", "cafe", "bar", "pub", "fast_food"):
        return True
    if (tags.get("building:use") or "").lower() in ("mixed", "residential;commercial"):
        return True
    if (tags.get("landuse") or "").lower() in ("mixed", "mixed_use"):
        return True
    return False


def _is_low_rent_explicit(tags: dict) -> bool:
    """Tags que marcan explícitamente vivienda asequible / social."""
    if (tags.get("social_housing") or "").lower() == "yes":
        return True
    if (tags.get("building") or "").lower() in ("public_housing", "council_house"):
        return True
    return False


# ── Clasificadores residenciales ────────────────────────────────────────────

def classify_apartment(tags: dict, area_m2: float | None = None) -> str:
    """
    Edificio de apartamentos → uno de los 4 sub-tipos residenciales CS2:
      - 'mixed'    → Mixed Housing (comercio abajo + aptos)
      - 'low_rent' → Low Rent Housing (bloques grandes asequibles)
      - 'high'     → High Density Housing (torres 7+ pisos)
      - 'med'      → Medium Density Housing (default, aptos pequeños)
    """
    if _is_apartment_mixed(tags):
        return "mixed"

    if _is_low_rent_explicit(tags):
        return "low_rent"

    building = (tags.get("building") or "").lower()
    if building in ("tower", "residential_tower", "skyscraper"):
        return "high"

    eff = _effective_levels(tags)
    if eff >= 7:
        return "high"

    # Heurística Low Rent: 4-6 pisos + footprint grande (≥1500 m²)
    if 4 <= eff <= 6 and area_m2 is not None and area_m2 >= 1500:
        return "low_rent"

    return "med"


def classify_residential_subtype(tags: dict) -> str | None:
    """
    Clasificar building tag específico (NO apartments).
      - 'low_house' → casas detached / single-family
      - 'row'       → row/town houses
      - None        → no es un subtipo reconocido (caller debe decidir)
    """
    building = (tags.get("building") or "").lower()
    residential = (tags.get("residential") or "").lower()

    if building in ("house", "detached", "bungalow"):
        return "low_house"

    if building in ("terrace", "townhouse", "row_house",
                    "semi", "semi_detached", "semidetached_house", "dormitory"):
        return "row"

    if residential in ("townhouse", "semi", "dormitory"):
        return "row"

    return None


def classify_landuse_residential(tags: dict) -> str:
    """
    Fallback para polígonos landuse=residential sin building específico.
    Asume Low Density Housing (suburbio típico de Minneapolis).
    """
    return "low_house"


# ── Clasificador comercial ──────────────────────────────────────────────────

def classify_commercial(tags: dict, area_m2: float | None = None) -> str:
    """
    Comercial → 'high' o 'low'.

    HIGH: malls, hoteles grandes, cines, teatros, casinos, conference centres,
          y commercial buildings con 4+ niveles o footprint grande.
    LOW:  default — shops, restaurantes, gas stations, cafés, fast food.
    """
    shop = (tags.get("shop") or "").lower()
    amenity = (tags.get("amenity") or "").lower()
    tourism = (tags.get("tourism") or "").lower()
    building = (tags.get("building") or "").lower()

    if shop == "mall":
        return "high"
    if amenity in ("cinema", "theatre", "casino", "conference_centre"):
        return "high"
    if tourism == "hotel":
        if _effective_levels(tags) >= 4 or (area_m2 is not None and area_m2 >= 2000):
            return "high"
        return "low"

    if building == "commercial" and _effective_levels(tags) >= 4:
        return "high"

    if _effective_levels(tags) >= 5:
        return "high"

    return "low"


# ── Clasificador oficinas ───────────────────────────────────────────────────

def classify_office(tags: dict) -> str:
    """
    Oficinas → 'high' o 'low'.

    HIGH: skyscrapers, building=office con 4+ niveles efectivos.
    LOW:  default — oficinas pequeñas en edificios bajos.
    """
    if (tags.get("building") or "").lower() == "skyscraper":
        return "high"
    if _effective_levels(tags) >= 4:
        return "high"
    return "low"


# ── Clasificador parking (sin cambios) ──────────────────────────────────────

def classify_parking(tags: dict) -> str:
    """
    Distinguir estacionamiento estructural (ramp/garage) de superficie.
    """
    parking_type = (tags.get("parking") or "").lower()
    if parking_type in ("multi-storey", "multistorey", "structure", "underground"):
        return "ramp"
    return "surface"


# ── Generic building=yes — spatial join + area heurística ───────────────────

# Mapa de landuse=* → CS2 key directa (para buildings sin tipo, clasificados
# por el polígono landuse que los contiene espacialmente).
LANDUSE_TO_CS2_KEY = {
    "residential": "res_low_house",
    "commercial":  "com_low",
    "retail":      "com_low",
    "industrial":  "industrial",
    "office":      "office_low",
}


def classify_generic_building_by_area(area_m2: float) -> str:
    """
    Heurística defensiva para building=yes sin contexto de landuse.

    Devuelve una CS2 key COMPLETA (no suffix). Pensado para footprints sin
    tipificar donde el spatial join contra landuse no encontró match. Es
    aproximada por diseño — un kiosco y una casa se diferencian solo por
    área. Útil en zonas con OSM esparso (small towns LATAM/Asia/África).

    Reglas:
      area < 300 m²  → res_low_house  (casa / construcción pequeña)
      area < 1500 m² → res_med        (edificio mediano genérico)
      area ≥ 1500 m² → industrial     (footprint grande sin contexto)
    """
    if area_m2 < 300:
        return "res_low_house"
    if area_m2 < 1500:
        return "res_med"
    return "industrial"


# ── Amenity cross-reference (v3.3.7) ────────────────────────────────────────

# Tags amenity=* que sugieren uso civic/community (NO industrial, NO residential).
# Si un building está cerca (≤30m) de un node con uno de estos tags, su clasificación
# heurística por área se sobreescribe a com_low (Low Density Business) que es el
# match más cercano en CS2 — no hay zona civic explícita en el modelo CS2.
CIVIC_AMENITIES = frozenset({
    # Educación
    "school", "university", "college", "kindergarten",
    # Salud
    "hospital", "clinic", "doctors", "dentist", "pharmacy",
    # Religión
    "place_of_worship",
    # Gobierno / Cívico
    "townhall", "courthouse", "public_building",
    "police", "fire_station", "post_office",
    # Cultura / Comunidad
    "library", "community_centre", "social_facility",
    "theatre", "arts_centre", "cinema",
    # Funerario / Cemeterios
    "funeral_hall", "crematorium",
})


def is_civic_amenity_tag(amenity_value: str) -> bool:
    """True si el valor de amenity=* es civic/community."""
    return (amenity_value or "").lower() in CIVIC_AMENITIES
