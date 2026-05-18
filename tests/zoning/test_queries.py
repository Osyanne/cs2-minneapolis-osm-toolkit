"""Tests de sanidad para los builders de queries Overpass (Sesión 1.6)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from zoning.zones import build_queries, CS2_LABELS

BBOX = "44.86,-93.38,45.05,-93.17"

# Las 10 source queries del modelo CS2-aligned (v3.3.7 añadió civic_amenities
# para amenity cross-reference; v3.3.4 añadió generic_buildings).
EXPECTED_SOURCE_KEYS = {
    "mixed_apartments",
    "apartments",
    "landuse_residential",
    "residential_subtypes",
    "commercial",
    "office",
    "industrial",
    "parking",
    "generic_buildings",
    "civic_amenities",
}

# Las 13 zonas CS2 del modelo realineado
EXPECTED_CS2_KEYS = {
    "res_low_house", "res_row", "res_med",
    "res_mixed", "res_low_rent", "res_high",
    "com_low", "com_high",
    "office_low", "office_high",
    "industrial",
    "prk_surface", "prk_ramp",
}


def test_all_expected_source_keys_present():
    queries = build_queries(BBOX)
    assert EXPECTED_SOURCE_KEYS == set(queries.keys())


def test_all_queries_contain_bbox():
    queries = build_queries(BBOX)
    for key, q in queries.items():
        assert BBOX in q, f"Query '{key}' no contiene el bbox"


def test_all_queries_have_out_directive():
    """Toda query Overpass debe terminar con un 'out' directive."""
    queries = build_queries(BBOX)
    for key, q in queries.items():
        # civic_amenities solo trae nodes → 'out body' (sin geom porque nodes no
        # tienen geometry separada). Las demás traen ways/relations → 'out body geom'.
        if key == "civic_amenities":
            assert "out body" in q, f"Query '{key}' no tiene 'out body'"
        else:
            assert "out body geom" in q, f"Query '{key}' no tiene 'out body geom'"


def test_all_queries_have_timeout():
    queries = build_queries(BBOX)
    for key, q in queries.items():
        assert "[timeout:" in q, f"Query '{key}' no tiene timeout"


def test_cs2_labels_has_all_zones():
    """Las 13 zonas del modelo CS2-aligned deben estar en CS2_LABELS."""
    assert EXPECTED_CS2_KEYS == set(CS2_LABELS.keys())


def test_cs2_labels_no_legacy_keys():
    """Las keys viejas (retail, mixed, mixed_res_com, office, res_low) no deben existir."""
    for legacy in ("retail", "mixed", "mixed_res_com", "office", "res_low"):
        assert legacy not in CS2_LABELS, f"Key legacy '{legacy}' debería estar eliminada"


def test_apartments_query_detects_mixed_signals():
    """La query de apartments debe traer apartments + variantes que marcan mixed/low_rent."""
    q = build_queries(BBOX)["apartments"]
    assert 'building"="apartments"' in q
    assert 'building"="public_housing"' in q
    assert 'social_housing"="yes"' in q


def test_commercial_query_includes_amenities():
    """La query commercial debe traer shops, restaurants, hoteles, malls, etc."""
    q = build_queries(BBOX)["commercial"]
    for needed in ('shop"]', 'amenity"="restaurant"', 'tourism"="hotel"',
                   'amenity"="cinema"', 'building"="supermarket"'):
        assert needed in q, f"commercial query falta {needed}"


def test_residential_subtypes_query_includes_row_housing():
    q = build_queries(BBOX)["residential_subtypes"]
    for needed in ('building"="terrace"', 'building"="townhouse"',
                   'building"="house"', 'building"="detached"'):
        assert needed in q, f"residential_subtypes query falta {needed}"


def test_office_query_separate_from_commercial():
    """La query de office NO debe traer shop/amenity (esos son commercial)."""
    q = build_queries(BBOX)["office"]
    assert 'building"="office"' in q
    assert 'shop"]' not in q
    assert 'amenity"="restaurant"' not in q


def test_mixed_apartments_uses_spatial_join():
    """La query mixed_apartments debe usar around.comm para spatial join."""
    q = build_queries(BBOX)["mixed_apartments"]
    assert "around.comm:5" in q, "mixed_apartments debe hacer spatial join around.comm:5"
    # Debe traer apartments y residential como objetivo del spatial join
    assert 'building"="apartments"' in q
    assert 'building"="residential"' in q
    # Debe definir .comm con nodos comerciales
    assert 'node["shop"]' in q
    assert 'node["amenity"="restaurant"]' in q
    # Debe incluir también tags directos de mixed-use
    assert 'building"="mixed_use"' in q
    assert 'building:use"="mixed"' in q


def test_generic_buildings_query_targets_building_yes():
    """generic_buildings recoge solo building=yes (footprints sin tipificar)."""
    q = build_queries(BBOX)["generic_buildings"]
    assert 'way["building"="yes"]' in q
    assert 'relation["building"="yes"]' in q
    # NO debe traer building=apartments u otros tipos ya capturados
    assert 'building"="apartments"' not in q
    assert 'building"="house"' not in q


def test_civic_amenities_query_captures_civic_tags():
    """civic_amenities recoge nodes amenity=school/hospital/church/etc."""
    q = build_queries(BBOX)["civic_amenities"]
    # Debe traer nodes (no ways) — amenity POIs son típicamente nodes
    assert 'node["amenity"' in q
    # Debe incluir las categorías clave
    for amenity in ("school", "hospital", "place_of_worship", "library",
                    "fire_station", "kindergarten"):
        assert amenity in q, f"civic_amenities query falta '{amenity}'"
