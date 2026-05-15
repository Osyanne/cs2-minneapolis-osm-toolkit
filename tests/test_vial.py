"""Tests del módulo vial (Sesión 2)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


BBOX = "44.86,-93.38,45.05,-93.17"

# Las 6 categorías viales CS2
EXPECTED_VIAL_KEYS = {"highway", "major", "minor", "local", "pedestrian", "bike"}


def test_vial_labels_has_six_keys():
    from vial_zones import VIAL_LABELS
    assert set(VIAL_LABELS.keys()) == EXPECTED_VIAL_KEYS


def test_vial_labels_are_human_readable():
    from vial_zones import VIAL_LABELS
    assert VIAL_LABELS["highway"] == "Highway"
    assert VIAL_LABELS["major"] == "Major Road"
    assert VIAL_LABELS["minor"] == "Minor Road"
    assert VIAL_LABELS["local"] == "Local Street"
    assert VIAL_LABELS["pedestrian"] == "Pedestrian Path"
    assert VIAL_LABELS["bike"] == "Bike Lane"


def test_build_vial_query_contains_bbox_and_all_highway_tags():
    from vial_zones import build_vial_query
    q = build_vial_query(BBOX)
    # El bbox debe estar embebido
    assert BBOX in q
    # Todas las categorías highway deben aparecer en la regex
    for tag in [
        "motorway", "motorway_link", "trunk", "trunk_link",
        "primary", "primary_link", "secondary", "secondary_link",
        "tertiary", "tertiary_link",
        "residential", "unclassified",
        "living_street", "service",
        "pedestrian", "footway", "path", "steps", "cycleway",
    ]:
        assert tag in q, f"falta '{tag}' en query"
    # Debe ser una sola query con out body geom
    assert "out body geom" in q
    assert "[out:json]" in q


# ── classifier tests ─────────────────────────────────────────────────────────

def test_classify_highway_motorway_and_link():
    from vial_classifiers import classify_highway
    assert classify_highway({"highway": "motorway"}) == "highway"
    assert classify_highway({"highway": "motorway_link"}) == "highway"
    assert classify_highway({"highway": "trunk"}) == "highway"
    assert classify_highway({"highway": "trunk_link"}) == "highway"


def test_classify_highway_major():
    from vial_classifiers import classify_highway
    assert classify_highway({"highway": "primary"}) == "major"
    assert classify_highway({"highway": "primary_link"}) == "major"
    assert classify_highway({"highway": "secondary"}) == "major"
    assert classify_highway({"highway": "secondary_link"}) == "major"


def test_classify_highway_minor():
    from vial_classifiers import classify_highway
    assert classify_highway({"highway": "tertiary"}) == "minor"
    assert classify_highway({"highway": "tertiary_link"}) == "minor"
    assert classify_highway({"highway": "residential"}) == "minor"
    assert classify_highway({"highway": "unclassified"}) == "minor"


def test_classify_highway_local():
    from vial_classifiers import classify_highway
    assert classify_highway({"highway": "living_street"}) == "local"
    assert classify_highway({"highway": "service"}) == "local"


def test_classify_highway_pedestrian():
    from vial_classifiers import classify_highway
    assert classify_highway({"highway": "pedestrian"}) == "pedestrian"
    assert classify_highway({"highway": "footway"}) == "pedestrian"
    assert classify_highway({"highway": "path"}) == "pedestrian"
    assert classify_highway({"highway": "steps"}) == "pedestrian"


def test_classify_highway_bike():
    from vial_classifiers import classify_highway
    assert classify_highway({"highway": "cycleway"}) == "bike"


def test_classify_highway_unknown_returns_none():
    from vial_classifiers import classify_highway
    assert classify_highway({"highway": "bus_guideway"}) is None
    assert classify_highway({"highway": "raceway"}) is None
    assert classify_highway({}) is None  # sin tag highway
    assert classify_highway({"highway": ""}) is None
