"""Test the CLI entry point — argument parsing + orchestration."""
import sys
from pathlib import Path
from unittest.mock import patch
import pytest
from official_zoning.extract import main


def test_main_requires_city_arg(capsys):
    """Without --city, CLI exits with usage error."""
    with patch.object(sys, "argv", ["extract-official-zoning"]):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code != 0


def test_main_rejects_unknown_city(capsys):
    """City not in SOURCES registry exits with error."""
    with patch.object(sys, "argv", ["extract-official-zoning", "--city", "atlantis"]):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code != 0


def test_main_calls_source_pipeline_with_minneapolis(tmp_path, monkeypatch):
    """With --city minneapolis, the Mpls source's download + read are called."""
    import geopandas as gpd
    from shapely.geometry import Polygon

    # Mock GDF uses the real Mpls 2040 Plan schema: Land_Use_C in EPSG:3857.
    # UN1 maps to res_low_house in minneapolis.yaml.
    fake_gdf = gpd.GeoDataFrame(
        {
            "Land_Use_C": ["UN1"],
            "geometry": [Polygon([(-10380000, 5610000), (-10379900, 5610000), (-10379900, 5610100), (-10380000, 5610100)])],
        },
        crs="EPSG:3857",
    )
    fake_cache = tmp_path / "mpls.zip"
    fake_cache.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    with patch("official_zoning.sources.minneapolis.download", return_value=fake_cache) as m_dl, \
         patch("official_zoning.sources.minneapolis.read", return_value=fake_gdf) as m_rd:
        with patch.object(sys, "argv", [
            "extract-official-zoning",
            "--city", "minneapolis",
            "--out-dir", str(out_dir),
        ]):
            main()

    m_dl.assert_called_once()
    m_rd.assert_called_once_with(fake_cache)
    expected_out = out_dir / "datos_zonificacion_official.js"
    assert expected_out.exists()
