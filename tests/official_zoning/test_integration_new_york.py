"""End-to-end integration test for the New York pipeline (mocked + network)."""
from pathlib import Path
import pytest
import geopandas as gpd
from shapely.geometry import Polygon

from official_zoning.sources import new_york
from official_zoning.mapping import load_mapping
from official_zoning.pipeline import process
from official_zoning.emitter import emit


MAPPING_PATH = Path(__file__).parent.parent.parent / "src" / "official_zoning" / "mappings" / "new_york.yaml"
NY_BBOX = [40.70, -74.02, 40.88, -73.90]  # Manhattan, matches cities.json


def test_integration_mocked_gdf_produces_valid_js(tmp_path):
    """Skip the network — use a mocked GeoDataFrame to exercise the rest of the chain."""
    mapping = load_mapping(MAPPING_PATH)
    # NY State Plane Long Island (EPSG:2263) — coords are in US Feet
    gdf = gpd.GeoDataFrame(
        {
            "ZONEDIST": ["R1-1", "C6-4", "M1-1", "R8A"],
            "geometry": [
                Polygon([(987000, 211000), (987500, 211000), (987500, 211500), (987000, 211500)]),
                Polygon([(988000, 211000), (988500, 211000), (988500, 211500), (988000, 211500)]),
                Polygon([(989000, 211000), (989500, 211000), (989500, 211500), (989000, 211500)]),
                Polygon([(990000, 211000), (990500, 211000), (990500, 211500), (990000, 211500)]),
            ],
        },
        crs="EPSG:2263",
    )
    result = process(gdf, mapping, NY_BBOX)
    out_path = tmp_path / "datos_zonificacion_official.js"
    emit(result, out_path, source_name="NYC Department of City Planning")

    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8")
    assert "DATA_OFFICIAL_RES_LOW_HOUSE" in content
    assert "DATA_OFFICIAL_COM_HIGH" in content
    assert "DATA_OFFICIAL_INDUSTRIAL" in content
    assert "DATA_OFFICIAL_RES_HIGH" in content


@pytest.mark.network
def test_integration_full_pipeline_real_data(tmp_path):
    """Full network roundtrip — download real NYC shapefile, emit JS."""
    mapping = load_mapping(MAPPING_PATH)
    cache_path = new_york.download(tmp_path, force_refresh=True)
    gdf = new_york.read(cache_path)
    result = process(gdf, mapping, NY_BBOX)
    out_path = tmp_path / "datos_zonificacion_official.js"
    emit(result, out_path, source_name="NYC Department of City Planning")

    assert out_path.exists()
    assert out_path.stat().st_size > 500_000  # NYC data is much bigger than Mpls
