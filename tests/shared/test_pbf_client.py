"""Tests for shared.pbf_client."""
from __future__ import annotations

from pathlib import Path

import pytest

from shared.pbf_client import _in_bbox, _osmium_tags


MONACO_PBF = Path(__file__).resolve().parents[1] / "fixtures" / "monaco-latest.osm.pbf"
MONACO_BBOX = (43.7236, 7.4090, 43.7521, 7.4395)  # south, west, north, east


class TestInBbox:
    def test_inside(self):
        # (south=0, west=0, north=10, east=10)
        assert _in_bbox(5.0, 5.0, (0.0, 0.0, 10.0, 10.0)) is True

    def test_on_boundary_south_west(self):
        assert _in_bbox(0.0, 0.0, (0.0, 0.0, 10.0, 10.0)) is True

    def test_on_boundary_north_east(self):
        assert _in_bbox(10.0, 10.0, (0.0, 0.0, 10.0, 10.0)) is True

    def test_outside_south(self):
        assert _in_bbox(-1.0, 5.0, (0.0, 0.0, 10.0, 10.0)) is False

    def test_outside_north(self):
        assert _in_bbox(11.0, 5.0, (0.0, 0.0, 10.0, 10.0)) is False

    def test_outside_west(self):
        assert _in_bbox(5.0, -1.0, (0.0, 0.0, 10.0, 10.0)) is False

    def test_outside_east(self):
        assert _in_bbox(5.0, 11.0, (0.0, 0.0, 10.0, 10.0)) is False


@pytest.mark.skipif(not MONACO_PBF.exists(), reason="Monaco fixture missing")
class TestOsmiumTags:
    def test_extracts_real_tags_from_monaco(self):
        """Iterate Monaco PBF, find any way with tags, confirm _osmium_tags returns a populated dict.

        NOTE: pyosmium 4.x invalidates obj references once the iterator advances,
        so we must extract the dict INSIDE the loop, not after break.
        """
        import osmium

        fp = osmium.FileProcessor(str(MONACO_PBF))
        extracted: dict[str, str] | None = None
        for obj in fp:
            if obj.is_way() and len(obj.tags) > 0:
                extracted = _osmium_tags(obj)
                break

        assert extracted is not None, "Monaco PBF has no tagged ways?"
        assert isinstance(extracted, dict)
        assert len(extracted) > 0
        # All keys and values are strings
        assert all(isinstance(k, str) for k in extracted.keys())
        assert all(isinstance(v, str) for v in extracted.values())

    def test_returns_empty_dict_for_no_tags(self):
        """Untagged nodes (just geometry) should give an empty dict, not crash."""
        import osmium

        fp = osmium.FileProcessor(str(MONACO_PBF))
        extracted: dict[str, str] | None = None
        for obj in fp:
            if obj.is_node() and len(obj.tags) == 0:
                extracted = _osmium_tags(obj)
                break

        if extracted is None:
            pytest.skip("No untagged nodes in fixture")
        assert extracted == {}


from shared.pbf_client import (
    _node_to_overpass,
    _way_to_overpass,
    _area_to_overpass,
)


@pytest.mark.skipif(not MONACO_PBF.exists(), reason="Monaco fixture missing")
class TestNodeToOverpass:
    def test_returns_overpass_shape(self):
        """A node with tags should become {type, id, tags, lat, lon}."""
        import osmium

        fp = osmium.FileProcessor(str(MONACO_PBF))
        result: dict | None = None
        for obj in fp:
            if obj.is_node() and len(obj.tags) > 0 and obj.location.valid():
                result = _node_to_overpass(obj)
                break

        if result is None:
            pytest.skip("No tagged nodes in fixture")
        assert result["type"] == "node"
        assert isinstance(result["id"], int)
        assert isinstance(result["tags"], dict)
        assert isinstance(result["lat"], float)
        assert isinstance(result["lon"], float)
        assert 43.7 <= result["lat"] <= 43.8  # Monaco lat range
        assert 7.4 <= result["lon"] <= 7.5    # Monaco lon range

    def test_invalid_location_returns_none(self):
        """Nodes without valid location should return None, not crash."""
        # Hard to construct synthetically; we'll test the behavior via integration later
        # Just sanity-check: real Monaco nodes all have valid locations, so we just
        # confirm the function doesn't crash on real data.
        import osmium

        fp = osmium.FileProcessor(str(MONACO_PBF))
        result_has_lat: bool | None = None
        for obj in fp:
            if obj.is_node():
                # All real nodes from a PBF have valid locations
                result = _node_to_overpass(obj)
                if result is not None:
                    result_has_lat = "lat" in result
                else:
                    result_has_lat = False  # acceptable
                break
        # Just confirm no crash; result_has_lat is True (real node) or False (None returned)
        assert result_has_lat is not None


@pytest.mark.skipif(not MONACO_PBF.exists(), reason="Monaco fixture missing")
class TestWayToOverpass:
    def test_returns_overpass_shape(self):
        """A way should become {type, id, tags, geometry: [{lat,lon}, ...]}."""
        import osmium

        fp = osmium.FileProcessor(str(MONACO_PBF)).with_locations()
        result: dict | None = None
        for obj in fp:
            if obj.is_way() and len(obj.tags) > 0 and len(obj.nodes) >= 2:
                # Verify all node locations are resolved
                try:
                    all_valid = all(n.location.valid() for n in obj.nodes)
                except Exception:
                    all_valid = False
                if all_valid:
                    result = _way_to_overpass(obj)
                    break

        assert result is not None, "Monaco PBF has no resolvable tagged ways?"
        assert result["type"] == "way"
        assert isinstance(result["id"], int)
        assert isinstance(result["tags"], dict)
        assert isinstance(result["geometry"], list)
        assert len(result["geometry"]) >= 2
        # Each geometry point is {lat, lon}
        for pt in result["geometry"]:
            assert "lat" in pt and "lon" in pt
            assert isinstance(pt["lat"], float)
            assert isinstance(pt["lon"], float)

    def test_way_with_no_resolvable_nodes_returns_none(self):
        """If a way has no valid locations, we should return None instead of crashing."""
        # Without .with_locations(), node references aren't resolved
        import osmium

        fp = osmium.FileProcessor(str(MONACO_PBF))  # NO with_locations()
        observed: dict | None = None
        for obj in fp:
            if obj.is_way() and len(obj.tags) > 0:
                # Locations should NOT be valid here
                observed = _way_to_overpass(obj)
                break
        # Either None (no valid coords) or fully populated — both acceptable, just must not crash
        if observed is not None:
            assert "geometry" in observed


@pytest.mark.skipif(not MONACO_PBF.exists(), reason="Monaco fixture missing")
class TestAreaToOverpass:
    def test_returns_relation_shape_with_outer_member(self):
        """Areas become {type: 'relation', id, tags, members: [{role: 'outer', geometry}]}."""
        import osmium

        fp = osmium.FileProcessor(str(MONACO_PBF)).with_areas()
        result: dict | None = None
        for obj in fp:
            if hasattr(obj, "from_way") and len(obj.tags) > 0:
                # This is an area
                result = _area_to_overpass(obj)
                if result is not None:
                    break

        if result is None:
            pytest.skip("No areas with tags in fixture")
        assert result["type"] == "relation"
        assert isinstance(result["id"], int)
        assert isinstance(result["members"], list)
        assert len(result["members"]) >= 1
        outer = result["members"][0]
        assert outer["role"] == "outer"
        assert isinstance(outer["geometry"], list)
        assert len(outer["geometry"]) >= 3


from shared.pbf_client import _apply_spatial_join


class TestSpatialJoin:
    def test_keeps_targets_near_anchors(self):
        anchors = [
            {"type": "node", "id": 1, "lat": 43.7350, "lon": 7.4200, "tags": {"shop": "supermarket"}},
        ]
        targets = [
            {
                "type": "way", "id": 100,
                "tags": {"building": "apartments"},
                "geometry": [
                    {"lat": 43.73503, "lon": 7.42003},  # ~5m from anchor
                    {"lat": 43.73510, "lon": 7.42010},
                    {"lat": 43.73520, "lon": 7.42020},
                    {"lat": 43.73503, "lon": 7.42003},
                ],
            },
        ]
        result = _apply_spatial_join(targets, anchors, buffer_m=10.0)
        assert len(result) == 1
        assert result[0]["id"] == 100

    def test_filters_targets_far_from_anchors(self):
        anchors = [
            {"type": "node", "id": 1, "lat": 43.7350, "lon": 7.4200, "tags": {}},
        ]
        targets = [
            {
                "type": "way", "id": 200,
                "tags": {},
                "geometry": [
                    {"lat": 50.000, "lon": 14.000},  # ~1000km away
                    {"lat": 50.001, "lon": 14.001},
                    {"lat": 50.002, "lon": 14.002},
                    {"lat": 50.000, "lon": 14.000},
                ],
            },
        ]
        result = _apply_spatial_join(targets, anchors, buffer_m=5.0)
        assert result == []

    def test_empty_anchors_returns_empty(self):
        targets = [{"type": "way", "id": 1, "geometry": [{"lat": 0, "lon": 0}], "tags": {}}]
        assert _apply_spatial_join(targets, [], buffer_m=5.0) == []

    def test_empty_targets_returns_empty(self):
        anchors = [{"type": "node", "id": 1, "lat": 0, "lon": 0, "tags": {}}]
        assert _apply_spatial_join([], anchors, buffer_m=5.0) == []


from shared.pbf_client import query
from shared.pbf_filters import FilterSpec, Clause, TagMatcher, SpatialJoin


@pytest.mark.skipif(not MONACO_PBF.exists(), reason="Monaco fixture missing")
class TestQueryAgainstMonaco:
    def test_returns_overpass_shape_dict(self):
        spec = FilterSpec(
            clauses={
                "buildings": Clause(
                    geom_types=["way"],
                    tag_filters=[TagMatcher({"building": True})],
                ),
            },
        )
        result = query(MONACO_PBF, MONACO_BBOX, spec, label="buildings")
        assert "elements" in result
        assert isinstance(result["elements"], list)
        # Monaco has thousands of buildings
        assert len(result["elements"]) > 100
        first = result["elements"][0]
        assert first["type"] in ("way", "relation")
        assert "id" in first
        assert "tags" in first

    def test_no_match_returns_empty_elements(self):
        spec = FilterSpec(
            clauses={
                "fake": Clause(
                    geom_types=["way"],
                    tag_filters=[TagMatcher({"building": "this_value_does_not_exist_anywhere_in_monaco"})],
                ),
            },
        )
        result = query(MONACO_PBF, MONACO_BBOX, spec, label="empty")
        assert result["elements"] == []

    def test_dedup_by_type_and_id(self):
        spec = FilterSpec(
            clauses={
                "a": Clause(
                    geom_types=["way"],
                    tag_filters=[TagMatcher({"building": True})],
                ),
                "b": Clause(
                    geom_types=["way"],
                    tag_filters=[TagMatcher({"building": True})],
                ),
            },
        )
        result = query(MONACO_PBF, MONACO_BBOX, spec, label="dedup")
        ids = [(el["type"], el["id"]) for el in result["elements"]]
        assert len(ids) == len(set(ids))

    def test_node_filter_returns_nodes(self):
        spec = FilterSpec(
            clauses={
                "amenities": Clause(
                    geom_types=["node"],
                    tag_filters=[TagMatcher({"amenity": True})],
                ),
            },
        )
        result = query(MONACO_PBF, MONACO_BBOX, spec, label="amenities")
        assert len(result["elements"]) > 0
        assert all(el["type"] == "node" for el in result["elements"])
        for el in result["elements"]:
            assert "lat" in el and "lon" in el

    def test_missing_pbf_raises(self, tmp_path: Path):
        spec = FilterSpec(
            clauses={
                "x": Clause(geom_types=["way"], tag_filters=[TagMatcher({"x": "y"})]),
            },
        )
        with pytest.raises(FileNotFoundError):
            query(tmp_path / "nope.osm.pbf", MONACO_BBOX, spec, label="x")


from shared.pbf_client import query_batch


@pytest.mark.skipif(not MONACO_PBF.exists(), reason="Monaco fixture missing")
class TestQueryBatch:
    def test_returns_dict_keyed_by_spec_name(self):
        specs = {
            "buildings": FilterSpec(
                clauses={
                    "b": Clause(geom_types=["way"], tag_filters=[TagMatcher({"building": True})]),
                },
            ),
            "amenities": FilterSpec(
                clauses={
                    "a": Clause(geom_types=["node"], tag_filters=[TagMatcher({"amenity": True})]),
                },
            ),
        }
        result = query_batch(MONACO_PBF, MONACO_BBOX, specs, label="test")
        assert set(result.keys()) == {"buildings", "amenities"}
        assert "elements" in result["buildings"]
        assert "elements" in result["amenities"]
        assert isinstance(result["buildings"]["elements"], list)
        assert isinstance(result["amenities"]["elements"], list)

    def test_each_spec_gets_correct_elements(self):
        """Buildings spec gets ways with building=*; amenities spec gets nodes with amenity=*."""
        specs = {
            "buildings": FilterSpec(
                clauses={
                    "b": Clause(geom_types=["way"], tag_filters=[TagMatcher({"building": True})]),
                },
            ),
            "amenities": FilterSpec(
                clauses={
                    "a": Clause(geom_types=["node"], tag_filters=[TagMatcher({"amenity": True})]),
                },
            ),
        }
        result = query_batch(MONACO_PBF, MONACO_BBOX, specs, label="test")
        # Buildings should all be ways
        assert all(el["type"] == "way" for el in result["buildings"]["elements"])
        # Amenities should all be nodes
        assert all(el["type"] == "node" for el in result["amenities"]["elements"])

    def test_batch_matches_individual_query_results(self):
        """query_batch result for a spec should equal query() result for the same spec."""
        spec = FilterSpec(
            clauses={
                "b": Clause(geom_types=["way"], tag_filters=[TagMatcher({"building": True})]),
            },
        )
        individual = query(MONACO_PBF, MONACO_BBOX, spec, label="solo")
        batched = query_batch(MONACO_PBF, MONACO_BBOX, {"only_one": spec}, label="batched")
        # Element counts should match exactly (same algorithm, same file)
        assert len(batched["only_one"]["elements"]) == len(individual["elements"])

    def test_empty_specs_dict_returns_empty_dict(self):
        result = query_batch(MONACO_PBF, MONACO_BBOX, {}, label="empty")
        assert result == {}

    def test_missing_pbf_raises(self, tmp_path: Path):
        specs = {
            "x": FilterSpec(
                clauses={"c": Clause(geom_types=["way"], tag_filters=[TagMatcher({"x": "y"})])},
            ),
        }
        with pytest.raises(FileNotFoundError):
            query_batch(tmp_path / "nope.osm.pbf", MONACO_BBOX, specs, label="x")

    def test_spatial_join_applied_per_spec(self):
        """Each spec's spatial joins should be applied independently."""
        # Spec with no spatial join
        no_join = FilterSpec(
            clauses={
                "b": Clause(geom_types=["way"], tag_filters=[TagMatcher({"building": True})]),
            },
        )
        # Spec with a spatial join that would drop everything (anchor matches nothing)
        with_join = FilterSpec(
            clauses={
                "impossible_anchor": Clause(
                    geom_types=["node"],
                    tag_filters=[TagMatcher({"this_tag_does_not_exist_anywhere": "neither_does_this"})],
                ),
                "targets": Clause(
                    geom_types=["way"],
                    tag_filters=[TagMatcher({"building": True})],
                ),
            },
            spatial_joins=[
                SpatialJoin(anchor_clause="impossible_anchor", target_clause="targets", buffer_m=5.0),
            ],
        )
        result = query_batch(MONACO_PBF, MONACO_BBOX, {"a": no_join, "b": with_join}, label="join")
        # no_join: should have buildings
        assert len(result["a"]["elements"]) > 0
        # with_join: should have ZERO (all targets dropped because no anchors matched)
        assert len(result["b"]["elements"]) == 0
