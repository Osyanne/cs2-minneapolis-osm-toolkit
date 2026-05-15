"""
Tests para classifiers.py — Sesión 1.6 (CS2-aligned model).
Ejecutar con: cd src && uv run pytest ../tests/test_classifiers.py -v
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from classifiers import (
    classify_apartment,
    classify_residential_subtype,
    classify_landuse_residential,
    classify_commercial,
    classify_office,
    classify_parking,
    polygon_area_m2,
    _effective_levels,
    _is_apartment_mixed,
    _is_low_rent_explicit,
)


# ══════════════════════════════════════════════════════════════════════════════
# Helpers (_effective_levels, polygon_area_m2)
# ══════════════════════════════════════════════════════════════════════════════

def test_effective_levels_from_tag():
    assert _effective_levels({"building:levels": "5"}) == 5

def test_effective_levels_from_height():
    """height/3 cuando faltan building:levels."""
    assert _effective_levels({"height": "18"}) == 6  # 18/3 = 6
    assert _effective_levels({"height": "9"}) == 3   # 9/3 = 3

def test_effective_levels_uses_max():
    """max(tagged, estimated) — protege contra discrepancias."""
    assert _effective_levels({"building:levels": "5", "height": "30"}) == 10

def test_effective_levels_invalid_height():
    """Strings raros no crashean."""
    assert _effective_levels({"height": "muy alto"}) == 0
    assert _effective_levels({"height": ""}) == 0

def test_effective_levels_no_tags():
    assert _effective_levels({}) == 0

def test_polygon_area_minneapolis_block():
    """Un cuadrado de ~100m x 100m en Minneapolis debe dar ~10000 m²."""
    # 100m en latitud ≈ 0.0009 grados a la latitud de Minneapolis (45°)
    # 100m en longitud ≈ 0.00127 grados (cos 45° ≈ 0.707)
    lat0 = 44.97
    lon0 = -93.27
    dlat = 100 / 111_320
    dlon = 100 / (111_320 * 0.7071)
    ring = [
        [lat0, lon0],
        [lat0 + dlat, lon0],
        [lat0 + dlat, lon0 + dlon],
        [lat0, lon0 + dlon],
    ]
    area = polygon_area_m2(ring)
    assert 9500 < area < 10500, f"Esperado ~10000 m², obtenido {area}"

def test_polygon_area_degenerate():
    """Polígonos con <3 puntos → 0."""
    assert polygon_area_m2([]) == 0.0
    assert polygon_area_m2([[44.97, -93.27]]) == 0.0
    assert polygon_area_m2([[44.97, -93.27], [44.98, -93.27]]) == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# classify_apartment — 4 outputs: high, mixed, low_rent, med
# ══════════════════════════════════════════════════════════════════════════════

def test_apartment_default_is_med():
    """Apartment sin levels sin tags → med (Medium Density Housing default)."""
    assert classify_apartment({}) == "med"

def test_apartment_2_levels_is_med():
    assert classify_apartment({"building:levels": "2"}) == "med"

def test_apartment_4_levels_small_is_med():
    """4 pisos pero footprint pequeño → med, NO low_rent."""
    assert classify_apartment({"building:levels": "4"}, area_m2=800) == "med"
    assert classify_apartment({"building:levels": "4"}, area_m2=None) == "med"

def test_apartment_4_levels_big_footprint_is_low_rent():
    """4-6 pisos + footprint ≥1500 m² → Low Rent (bloque grande asequible)."""
    assert classify_apartment({"building:levels": "4"}, area_m2=2000) == "low_rent"
    assert classify_apartment({"building:levels": "6"}, area_m2=3500) == "low_rent"

def test_apartment_7_levels_is_high():
    """7+ pisos → High Density Housing (torre residencial)."""
    assert classify_apartment({"building:levels": "7"}) == "high"
    assert classify_apartment({"building:levels": "12"}) == "high"
    assert classify_apartment({"building:levels": "20"}) == "high"

def test_apartment_tower_tag_is_high():
    assert classify_apartment({"building": "tower"}) == "high"
    assert classify_apartment({"building": "residential_tower"}) == "high"
    assert classify_apartment({"building": "skyscraper"}) == "high"

def test_apartment_with_shop_is_mixed():
    """Apartamento con shop=* en la misma vía → Mixed Housing."""
    assert classify_apartment({"shop": "supermarket"}) == "mixed"
    assert classify_apartment({"shop": "convenience"}) == "mixed"

def test_apartment_with_restaurant_amenity_is_mixed():
    assert classify_apartment({"amenity": "restaurant"}) == "mixed"
    assert classify_apartment({"amenity": "cafe"}) == "mixed"
    assert classify_apartment({"amenity": "bar"}) == "mixed"

def test_apartment_building_use_mixed_is_mixed():
    assert classify_apartment({"building:use": "mixed"}) == "mixed"
    assert classify_apartment({"building:use": "residential;commercial"}) == "mixed"

def test_apartment_public_housing_is_low_rent():
    assert classify_apartment({"building": "public_housing"}) == "low_rent"
    assert classify_apartment({"building": "council_house"}) == "low_rent"

def test_apartment_social_housing_yes_is_low_rent():
    assert classify_apartment({"social_housing": "yes"}) == "low_rent"

def test_apartment_mixed_wins_over_low_rent():
    """Si hay shop + social_housing, mixed gana (prioridad por orden)."""
    assert classify_apartment({
        "shop": "convenience", "social_housing": "yes"
    }) == "mixed"

def test_apartment_low_rent_wins_over_high():
    """social_housing + 8 pisos → low_rent (explicit beats heuristic)."""
    assert classify_apartment({
        "social_housing": "yes", "building:levels": "8"
    }) == "low_rent"

def test_apartment_height_18m_no_levels_is_high():
    """Fallback height/3 = 6, así que con 21m → 7 → high."""
    assert classify_apartment({"height": "21"}) == "high"


# ══════════════════════════════════════════════════════════════════════════════
# classify_residential_subtype — para building tags específicos
# ══════════════════════════════════════════════════════════════════════════════

def test_subtype_detached_house_is_low_house():
    assert classify_residential_subtype({"building": "house"}) == "low_house"
    assert classify_residential_subtype({"building": "detached"}) == "low_house"
    assert classify_residential_subtype({"building": "bungalow"}) == "low_house"

def test_subtype_terrace_is_row():
    assert classify_residential_subtype({"building": "terrace"}) == "row"
    assert classify_residential_subtype({"building": "townhouse"}) == "row"
    assert classify_residential_subtype({"building": "row_house"}) == "row"

def test_subtype_semi_is_row():
    assert classify_residential_subtype({"building": "semi"}) == "row"
    assert classify_residential_subtype({"building": "semi_detached"}) == "row"
    assert classify_residential_subtype({"building": "semidetached_house"}) == "row"

def test_subtype_dormitory_is_row():
    assert classify_residential_subtype({"building": "dormitory"}) == "row"

def test_subtype_residential_tag_townhouse():
    """Tag residential=townhouse → row."""
    assert classify_residential_subtype({"residential": "townhouse"}) == "row"

def test_subtype_apartment_returns_none():
    """No clasificar apartments aquí (los maneja classify_apartment)."""
    assert classify_residential_subtype({"building": "apartments"}) is None

def test_subtype_unrelated_returns_none():
    assert classify_residential_subtype({"building": "office"}) is None
    assert classify_residential_subtype({}) is None


# ══════════════════════════════════════════════════════════════════════════════
# classify_landuse_residential — fallback
# ══════════════════════════════════════════════════════════════════════════════

def test_landuse_residential_always_low_house():
    """Fallback genérico para landuse=residential sin building específico."""
    assert classify_landuse_residential({}) == "low_house"
    assert classify_landuse_residential({"landuse": "residential"}) == "low_house"


# ══════════════════════════════════════════════════════════════════════════════
# classify_commercial — high / low
# ══════════════════════════════════════════════════════════════════════════════

def test_commercial_default_is_low():
    """Comercial sin tags reveladores → low."""
    assert classify_commercial({}) == "low"

def test_commercial_shop_is_low():
    assert classify_commercial({"shop": "convenience"}) == "low"
    assert classify_commercial({"shop": "supermarket"}) == "low"

def test_commercial_restaurant_is_low():
    assert classify_commercial({"amenity": "restaurant"}) == "low"
    assert classify_commercial({"amenity": "fast_food"}) == "low"
    assert classify_commercial({"amenity": "fuel"}) == "low"

def test_commercial_mall_is_high():
    """Centro comercial → high."""
    assert classify_commercial({"shop": "mall"}) == "high"

def test_commercial_cinema_is_high():
    assert classify_commercial({"amenity": "cinema"}) == "high"
    assert classify_commercial({"amenity": "theatre"}) == "high"
    assert classify_commercial({"amenity": "casino"}) == "high"
    assert classify_commercial({"amenity": "conference_centre"}) == "high"

def test_commercial_hotel_small_is_low():
    """Motel/hotel pequeño → low."""
    assert classify_commercial({"tourism": "hotel", "building:levels": "2"}) == "low"
    assert classify_commercial({"tourism": "hotel"}, area_m2=500) == "low"

def test_commercial_hotel_tall_is_high():
    """Hotel grande → high."""
    assert classify_commercial({"tourism": "hotel", "building:levels": "8"}) == "high"

def test_commercial_hotel_big_footprint_is_high():
    """Hotel con footprint ≥2000 m² → high (aún sin levels)."""
    assert classify_commercial({"tourism": "hotel"}, area_m2=3000) == "high"

def test_commercial_building_commercial_4_floors_is_high():
    assert classify_commercial({"building": "commercial", "building:levels": "4"}) == "high"

def test_commercial_5_floors_is_high():
    """5+ pisos siempre high, sea cual sea el tag."""
    assert classify_commercial({"building:levels": "5"}) == "high"


# ══════════════════════════════════════════════════════════════════════════════
# classify_office — high / low
# ══════════════════════════════════════════════════════════════════════════════

def test_office_default_is_low():
    assert classify_office({}) == "low"
    assert classify_office({"building": "office"}) == "low"

def test_office_low_2_floors():
    assert classify_office({"building": "office", "building:levels": "2"}) == "low"
    assert classify_office({"building": "office", "building:levels": "3"}) == "low"

def test_office_high_4_floors():
    assert classify_office({"building": "office", "building:levels": "4"}) == "high"

def test_office_skyscraper_is_high():
    assert classify_office({"building": "skyscraper"}) == "high"

def test_office_high_uses_height():
    """Altura/3 como fallback igual que residencial/commercial."""
    assert classify_office({"height": "15"}) == "high"  # 15/3=5 → high
    assert classify_office({"height": "6"}) == "low"    # 6/3=2 → low


# ══════════════════════════════════════════════════════════════════════════════
# classify_parking (sin cambios desde Sesión 1.5)
# ══════════════════════════════════════════════════════════════════════════════

def test_parking_surface_default():
    assert classify_parking({}) == "surface"

def test_parking_ramp_multistorey():
    assert classify_parking({"parking": "multi-storey"}) == "ramp"
    assert classify_parking({"parking": "multistorey"}) == "ramp"

def test_parking_ramp_underground():
    assert classify_parking({"parking": "underground"}) == "ramp"

def test_parking_ramp_structure():
    assert classify_parking({"parking": "structure"}) == "ramp"


# ══════════════════════════════════════════════════════════════════════════════
# Helpers internos (smoke tests)
# ══════════════════════════════════════════════════════════════════════════════

def test_is_apartment_mixed_detects_all_signals():
    assert _is_apartment_mixed({"shop": "anything"})
    assert _is_apartment_mixed({"amenity": "restaurant"})
    assert _is_apartment_mixed({"building:use": "mixed"})
    assert _is_apartment_mixed({"landuse": "mixed_use"})
    assert not _is_apartment_mixed({})
    assert not _is_apartment_mixed({"amenity": "school"})

def test_is_low_rent_explicit_detects_all_signals():
    assert _is_low_rent_explicit({"social_housing": "yes"})
    assert _is_low_rent_explicit({"building": "public_housing"})
    assert _is_low_rent_explicit({"building": "council_house"})
    assert not _is_low_rent_explicit({})
    assert not _is_low_rent_explicit({"building": "apartments"})
