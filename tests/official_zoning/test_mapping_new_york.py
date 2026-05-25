"""Test the NYC mapping YAML — validates structure and core categories."""
from pathlib import Path
from official_zoning.mapping import load_mapping


MAPPING_PATH = Path(__file__).parent.parent.parent / "src" / "official_zoning" / "mappings" / "new_york.yaml"


def test_mapping_loads():
    m = load_mapping(MAPPING_PATH)
    assert m.city == "new_york"
    assert m.source_field in ("ZONEDIST", "Zoning_District", "ZoneDist1")
    assert m.crs_in.startswith("EPSG:")


def test_mapping_covers_residential():
    m = load_mapping(MAPPING_PATH)
    # NYC residential — R1-R10 prefixes (subdistricts after dash)
    for code in ("R1-1", "R2", "R3-1", "R4", "R5", "R6", "R7-1", "R8", "R9", "R10"):
        assert m.translate(code) is not None, f"missing mapping for {code}"


def test_mapping_covers_commercial():
    m = load_mapping(MAPPING_PATH)
    for code in ("C1-1", "C2-1", "C4-1", "C8-1"):
        assert m.translate(code) is not None, f"missing mapping for {code}"


def test_mapping_covers_manufacturing():
    m = load_mapping(MAPPING_PATH)
    for code in ("M1-1", "M2-1", "M3-1"):
        assert m.translate(code) == "industrial"
