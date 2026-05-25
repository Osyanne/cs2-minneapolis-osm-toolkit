"""Test fixtures for the official zoning module."""
import pytest
import geopandas as gpd
from shapely.geometry import Polygon


@pytest.fixture
def sample_zoning_gdf() -> gpd.GeoDataFrame:
    """Tiny 3-polygon GeoDataFrame in EPSG:26915 (MN State Plane South).

    Coords are roughly downtown Minneapolis in MN State Plane meters.
    Used to exercise the parse → reproject → filter → map pipeline without
    hitting the network or the filesystem.
    """
    geoms = [
        Polygon([(478000, 4980000), (478100, 4980000), (478100, 4980100), (478000, 4980100)]),
        Polygon([(478200, 4980000), (478300, 4980000), (478300, 4980100), (478200, 4980100)]),
        Polygon([(478400, 4980000), (478500, 4980000), (478500, 4980100), (478400, 4980100)]),
    ]
    return gpd.GeoDataFrame(
        {
            "ZONE_CODE": ["R1", "B4", "I1"],
            "geometry": geoms,
        },
        crs="EPSG:26915",
    )


@pytest.fixture
def sample_mapping_yaml(tmp_path):
    """Minimal mapping YAML for the sample fixture."""
    content = """city: test_city
source_url: https://example.test/zoning.zip
source_field: ZONE_CODE
crs_in: EPSG:26915
last_validated: 2026-05-24
mappings:
  R1: res_low_house
  B4: com_high
  I1: industrial
unmapped: skip
"""
    path = tmp_path / "test_city.yaml"
    path.write_text(content, encoding="utf-8")
    return path
