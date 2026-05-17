"""Tests del módulo services.zones (Sesión 3)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


BBOX = "44.86,-93.38,45.05,-93.17"

# Las 5 capas de servicios CS2
EXPECTED_SERVICES_KEYS = {"health", "education", "fire", "admin", "parks"}


def test_services_labels_has_five_keys():
    from services.zones import SERVICES_LABELS
    assert set(SERVICES_LABELS.keys()) == EXPECTED_SERVICES_KEYS


def test_services_labels_are_human_readable():
    from services.zones import SERVICES_LABELS
    assert SERVICES_LABELS["health"]    == "Atención sanitaria y funeraria"
    assert SERVICES_LABELS["education"] == "Educación e investigación"
    assert SERVICES_LABELS["fire"]      == "Bomberos"
    assert SERVICES_LABELS["admin"]     == "Policía y administración"
    assert SERVICES_LABELS["parks"]     == "Parques"


def test_services_colors_match_labels():
    from services.zones import SERVICES_LABELS, SERVICES_COLORS
    assert set(SERVICES_LABELS.keys()) == set(SERVICES_COLORS.keys())


def test_services_colors_have_color_and_char():
    from services.zones import SERVICES_COLORS
    for key, entry in SERVICES_COLORS.items():
        assert "color" in entry, f"falta 'color' en {key}"
        assert "char" in entry, f"falta 'char' en {key}"
        assert entry["color"].startswith("#"), f"color de {key} no es hex"
        assert len(entry["char"]) == 1, f"char de {key} debe ser 1 caracter"


def test_services_chars_are_unique():
    from services.zones import SERVICES_COLORS
    chars = [entry["char"] for entry in SERVICES_COLORS.values()]
    assert len(chars) == len(set(chars)), f"chars duplicados: {chars}"


def test_bbox_reexport_matches_vial():
    from services.zones import MINNEAPOLIS_BBOX
    from vial.zones import MINNEAPOLIS_BBOX as VIAL_BBOX
    assert MINNEAPOLIS_BBOX == VIAL_BBOX


def test_build_services_query_contains_bbox():
    from services.zones import build_services_query
    q = build_services_query(BBOX)
    assert BBOX in q


def test_build_services_query_contains_all_amenities():
    from services.zones import build_services_query
    q = build_services_query(BBOX)
    for amenity in [
        "hospital", "clinic", "doctors", "funeral_directors", "crematorium",
        "school", "university", "college", "kindergarten", "research_institute",
        "fire_station",
        "police", "townhall", "courthouse", "prison",
        "library", "theatre", "arts_centre", "cinema",
    ]:
        assert amenity in q, f"falta amenity '{amenity}' en query"


def test_build_services_query_contains_leisure():
    from services.zones import build_services_query
    q = build_services_query(BBOX)
    for leisure in ["park", "nature_reserve", "garden", "playground", "sports_centre"]:
        assert leisure in q, f"falta leisure '{leisure}' en query"


def test_build_services_query_cemetery_only_ways():
    from services.zones import build_services_query
    q = build_services_query(BBOX)
    assert 'way["landuse"="cemetery"]' in q
    assert 'node["landuse"="cemetery"]' not in q


def test_build_services_query_contains_office_and_tourism():
    from services.zones import build_services_query
    q = build_services_query(BBOX)
    assert "office" in q
    assert "government" in q
    assert "research" in q
    assert "tourism" in q
    assert "museum" in q


def test_build_services_query_uses_out_body_geom():
    from services.zones import build_services_query
    q = build_services_query(BBOX)
    assert "out body geom" in q
    assert "[out:json]" in q
