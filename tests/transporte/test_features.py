"""Test the build_route_feature converter (relation element → feature dict)."""
from transporte.extract import build_route_feature


def _make_relation(tags: dict, member_ways: list[list[list[float]]]) -> dict:
    """Helper: build a fake Overpass relation element."""
    return {
        "type": "relation",
        "id": 12345,
        "tags": tags,
        "members": [
            {"type": "way", "ref": i, "geometry": [{"lat": p[0], "lon": p[1]} for p in w]}
            for i, w in enumerate(member_ways)
        ],
    }


def test_build_route_feature_lrt_green_line():
    rel = _make_relation(
        {"route": "light_rail", "name": "METRO Green Line", "ref": "Green", "operator": "Metro Transit"},
        [[[1.0, 1.0], [2.0, 2.0]], [[2.0, 2.0], [3.0, 3.0]]],
    )
    feat = build_route_feature(rel, cs2_key="lrt")
    assert feat["name"] == "METRO Green Line"
    assert feat["ref"] == "Green"
    assert feat["operator"] == "Metro Transit"
    assert feat["osm_id"] == 12345
    assert feat["coords"] == [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]]


def test_build_route_feature_multi_segment_when_gap():
    """When member ways don't connect, feature uses the LONGEST segment."""
    rel = _make_relation(
        {"route": "bus", "name": "Route 5"},
        [[[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]],
         [[10.0, 10.0], [11.0, 11.0]]],
    )
    feat = build_route_feature(rel, cs2_key="bus")
    assert feat["coords"] == [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]]


def test_build_route_feature_missing_name_falls_back_to_ref():
    rel = _make_relation(
        {"route": "bus", "ref": "5"},
        [[[1.0, 1.0], [2.0, 2.0]]],
    )
    feat = build_route_feature(rel, cs2_key="bus")
    assert feat["name"] == "Route 5"


def test_build_route_feature_no_name_no_ref_uses_unknown():
    rel = _make_relation(
        {"route": "bus"},
        [[[1.0, 1.0], [2.0, 2.0]]],
    )
    feat = build_route_feature(rel, cs2_key="bus")
    assert feat["name"] == "Unknown route"


def test_build_route_feature_no_geometry_returns_none():
    rel = {"type": "relation", "id": 1, "tags": {"route": "bus"}, "members": []}
    assert build_route_feature(rel, cs2_key="bus") is None


def test_build_route_feature_truncates_coords_to_5_decimals():
    rel = _make_relation(
        {"route": "light_rail", "name": "X"},
        [[[44.9876543, -93.1234567], [44.9876544, -93.1234568]]],
    )
    feat = build_route_feature(rel, cs2_key="lrt")
    assert feat["coords"][0] == [44.98765, -93.12346]
    assert feat["coords"][1] == [44.98765, -93.12346]
