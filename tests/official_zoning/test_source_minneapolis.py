"""Test the Minneapolis source module — downloader + parser."""
from pathlib import Path
import pytest
from official_zoning.source_interface import Source
from official_zoning.sources import minneapolis


def test_minneapolis_source_implements_protocol():
    """The module exposes download() + read() + slug per the Source protocol."""
    assert minneapolis.slug == "minneapolis"
    assert callable(minneapolis.download)
    assert callable(minneapolis.read)


def test_minneapolis_module_registered_in_sources():
    from official_zoning.sources import SOURCES
    assert "minneapolis" in SOURCES
    assert SOURCES["minneapolis"] is minneapolis


def test_minneapolis_download_url_constant_set():
    """The module must declare DATA_URL pointing to the Mpls open data portal."""
    assert hasattr(minneapolis, "DATA_URL")
    assert minneapolis.DATA_URL.startswith("https://")
    assert "minneapolis" in minneapolis.DATA_URL.lower() or "opendata.minneapolismn.gov" in minneapolis.DATA_URL or "arcgis" in minneapolis.DATA_URL


@pytest.mark.network
def test_minneapolis_download_real_portal(tmp_path):
    """Network test — actually fetch the shapefile. Opt-in via -m network."""
    path = minneapolis.download(tmp_path, force_refresh=True)
    assert path.exists()
    assert path.stat().st_size > 10_000  # at least 10 KB


@pytest.mark.network
def test_minneapolis_read_returns_geodataframe_with_zone_code(tmp_path):
    """Network test — download + read returns valid GDF with ZONE_CODE column."""
    import geopandas as gpd
    path = minneapolis.download(tmp_path)
    gdf = minneapolis.read(path)
    assert isinstance(gdf, gpd.GeoDataFrame)
    assert "ZONE_CODE" in gdf.columns or "ZONING" in gdf.columns
    assert len(gdf) > 100
