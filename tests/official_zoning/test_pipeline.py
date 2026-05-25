"""Test the pipeline orchestrator — reproject, filter, map."""
import geopandas as gpd
from shapely.geometry import box
from official_zoning.pipeline import process
from official_zoning.mapping import load_mapping


def test_process_reprojects_to_wgs84(sample_zoning_gdf, sample_mapping_yaml):
    """Output GeoDataFrame must be in EPSG:4326 (WGS84 lat/lon)."""
    mapping = load_mapping(sample_mapping_yaml)
    bbox_wgs84 = [44.0, -94.0, 46.0, -92.0]  # generous bbox covering Mpls
    result = process(sample_zoning_gdf, mapping, bbox_wgs84)
    assert result.crs.to_string().upper() == "EPSG:4326"


def test_process_adds_cs2_zone_column(sample_zoning_gdf, sample_mapping_yaml):
    """Output must have a 'cs2_zone' column populated by mapping."""
    mapping = load_mapping(sample_mapping_yaml)
    result = process(sample_zoning_gdf, mapping, [44.0, -94.0, 46.0, -92.0])
    assert "cs2_zone" in result.columns
    assert set(result["cs2_zone"]) == {"res_low_house", "com_high", "industrial"}


def test_process_filters_by_bbox(sample_zoning_gdf, sample_mapping_yaml):
    """Polygons outside the bbox must be dropped."""
    mapping = load_mapping(sample_mapping_yaml)
    # Bbox in middle of the ocean — should drop all polygons
    tiny_bbox = [0.0, 0.0, 0.001, 0.001]
    result = process(sample_zoning_gdf, mapping, tiny_bbox)
    assert len(result) == 0


def test_process_drops_unmapped_when_strategy_skip(tmp_path):
    """Polygons whose code is not in the mapping must be dropped when strategy=SKIP."""
    from shapely.geometry import Polygon
    gdf = gpd.GeoDataFrame(
        {
            "ZONE_CODE": ["R1", "UNKNOWN"],
            "geometry": [
                Polygon([(478000, 4980000), (478100, 4980000), (478100, 4980100), (478000, 4980100)]),
                Polygon([(478200, 4980000), (478300, 4980000), (478300, 4980100), (478200, 4980100)]),
            ],
        },
        crs="EPSG:26915",
    )
    mapping_content = """city: t
source_url: https://example.test
source_field: ZONE_CODE
crs_in: EPSG:26915
last_validated: 2026-05-24
mappings:
  R1: res_low_house
unmapped: skip
"""
    p = tmp_path / "t.yaml"
    p.write_text(mapping_content, encoding="utf-8")
    mapping = load_mapping(p)
    result = process(gdf, mapping, [44.0, -94.0, 46.0, -92.0])
    assert len(result) == 1
    assert result.iloc[0]["cs2_zone"] == "res_low_house"
