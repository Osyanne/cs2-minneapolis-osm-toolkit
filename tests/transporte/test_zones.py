"""Test the TRANSPORT_LABELS dict and Overpass query builder."""
from transporte.zones import TRANSPORT_LABELS, build_transporte_query


def test_transport_labels_has_four_categories():
    assert set(TRANSPORT_LABELS.keys()) == {"lrt", "commuter", "brt", "bus"}


def test_transport_labels_are_human_readable():
    assert TRANSPORT_LABELS["lrt"] == "LRT"
    assert TRANSPORT_LABELS["commuter"] == "Commuter Rail"
    assert TRANSPORT_LABELS["brt"] == "BRT"
    assert TRANSPORT_LABELS["bus"] == "Bus"


def test_build_query_includes_all_route_types():
    q = build_transporte_query("44.86,-93.38,45.05,-93.17")
    assert "light_rail" in q
    assert "train" in q
    assert "tram" in q
    assert "bus" in q


def test_build_query_includes_bbox():
    q = build_transporte_query("44.86,-93.38,45.05,-93.17")
    assert "44.86,-93.38,45.05,-93.17" in q


def test_build_query_uses_relation_type():
    q = build_transporte_query("44.86,-93.38,45.05,-93.17")
    assert "relation" in q.lower()


def test_build_query_includes_out_body_geom():
    """Overpass `out body geom;` returns relation members with their way geometries."""
    q = build_transporte_query("0,0,1,1")
    assert "out body geom" in q
