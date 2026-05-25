"""End-to-end integration test for the Minneapolis pipeline."""
from pathlib import Path
import pytest
import geopandas as gpd
from shapely.geometry import Polygon

from official_zoning.sources import minneapolis
from official_zoning.mapping import load_mapping
from official_zoning.pipeline import process
from official_zoning.emitter import emit


MAPPING_PATH = Path(__file__).parent.parent.parent / "src" / "official_zoning" / "mappings" / "minneapolis.yaml"
# Same bbox as cities.json declares for minneapolis
MPLS_BBOX = [44.86, -93.38, 45.05, -93.17]


def test_integration_mocked_gdf_produces_valid_js(tmp_path):
    """Skip the network — use a mocked GeoDataFrame with the 2040 Plan schema."""
    mapping = load_mapping(MAPPING_PATH)
    # EPSG:3857 (Web Mercator) is what the Mpls portal publishes.
    # Coords below are inside the Mpls bbox after reprojection to WGS84.
    gdf = gpd.GeoDataFrame(
        {
            "Land_Use_C": ["UN1", "DT1", "PR1", "UN3"],
            "geometry": [
                Polygon([(-10380000, 5610000), (-10379900, 5610000), (-10379900, 5610100), (-10380000, 5610100)]),
                Polygon([(-10379800, 5610000), (-10379700, 5610000), (-10379700, 5610100), (-10379800, 5610100)]),
                Polygon([(-10379600, 5610000), (-10379500, 5610000), (-10379500, 5610100), (-10379600, 5610100)]),
                Polygon([(-10379400, 5610000), (-10379300, 5610000), (-10379300, 5610100), (-10379400, 5610100)]),
            ],
        },
        crs="EPSG:3857",
    )
    result = process(gdf, mapping, MPLS_BBOX)
    out_path = tmp_path / "datos_zonificacion_official.js"
    emit(result, out_path, source_name="Mpls 2040 Plan — Primary Land Use")

    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8")
    # UN1 → res_low_house, DT1 → com_high, PR1 → industrial, UN3 → res_med
    assert "DATA_OFFICIAL_RES_LOW_HOUSE" in content
    assert "DATA_OFFICIAL_COM_HIGH" in content
    assert "DATA_OFFICIAL_INDUSTRIAL" in content
    assert "DATA_OFFICIAL_RES_MED" in content


@pytest.mark.network
def test_integration_full_pipeline_real_data(tmp_path):
    """Full network roundtrip — download real Mpls shapefile, emit JS."""
    mapping = load_mapping(MAPPING_PATH)
    cache_path = minneapolis.download(tmp_path, force_refresh=True)
    gdf = minneapolis.read(cache_path)
    result = process(gdf, mapping, MPLS_BBOX)
    out_path = tmp_path / "datos_zonificacion_official.js"
    emit(result, out_path, source_name="City of Minneapolis Planning")

    assert out_path.exists()
    assert out_path.stat().st_size > 50_000  # real Mpls dataset is non-trivial
    # Sanity: at least 1000 polygons total across zones
    content = out_path.read_text(encoding="utf-8")
    import re
    coord_count = len(re.findall(r"\[\d", content))
    assert coord_count > 1000
