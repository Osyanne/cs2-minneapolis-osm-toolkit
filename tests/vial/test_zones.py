"""Tests for vial.zones.build_vial_pbf_filter."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from vial.zones import build_vial_pbf_filter
from shared.pbf_filters import FilterSpec


def test_returns_filterspec():
    f = build_vial_pbf_filter((44.86, -93.38, 45.05, -93.17))
    assert isinstance(f, FilterSpec)


def test_matches_motorway_and_residential_and_cycleway():
    f = build_vial_pbf_filter((44.86, -93.38, 45.05, -93.17))
    clause = next(iter(f.clauses.values()))
    assert any(m.matches({"highway": "motorway"}) for m in clause.tag_filters)
    assert any(m.matches({"highway": "residential"}) for m in clause.tag_filters)
    assert any(m.matches({"highway": "cycleway"}) for m in clause.tag_filters)


def test_does_not_match_random_tag():
    f = build_vial_pbf_filter((44.86, -93.38, 45.05, -93.17))
    clause = next(iter(f.clauses.values()))
    assert not any(m.matches({"building": "yes"}) for m in clause.tag_filters)
