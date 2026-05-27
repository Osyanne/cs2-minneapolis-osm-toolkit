"""Test the CLI entrypoint (mocked Overpass, no network)."""
import sys
import json
from pathlib import Path
from unittest.mock import patch
import pytest

from transporte.extract import main, parse_args


def test_parse_args_requires_city_or_bbox():
    """parse_args allows both to be None; main() validates."""
    args = parse_args([])
    assert args.city is None
    assert args.bbox is None


def test_parse_args_accepts_city_slug():
    args = parse_args(["--city", "minneapolis"])
    assert args.city == "minneapolis"


def test_parse_args_accepts_bbox_and_slug():
    args = parse_args(["--bbox", "44,-93,45,-92", "--slug", "test"])
    assert args.bbox == "44,-93,45,-92"
    assert args.slug == "test"


def test_main_exits_when_no_city_or_bbox(capsys):
    with patch.object(sys, "argv", ["extract-transporte"]):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code != 0


def test_main_writes_js_file_when_pipeline_succeeds(tmp_path, monkeypatch):
    """Full pipeline with mocked Overpass: writes datos_transporte.js + updates manifest."""
    fake_overpass = {
        "elements": [
            {
                "type": "relation",
                "id": 100,
                "tags": {"route": "light_rail", "name": "METRO Green Line", "ref": "Green"},
                "members": [
                    {"type": "way", "ref": 1, "geometry": [{"lat": 44.97, "lon": -93.27}, {"lat": 44.98, "lon": -93.26}]},
                ],
            },
            {
                "type": "relation",
                "id": 200,
                "tags": {"route": "bus", "name": "Route 5"},
                "members": [
                    {"type": "way", "ref": 2, "geometry": [{"lat": 44.96, "lon": -93.25}, {"lat": 44.95, "lon": -93.24}]},
                ],
            },
        ]
    }
    cities_data = {
        "minneapolis": {
            "display_name": "Minneapolis, MN",
            "bbox": [44.86, -93.38, 45.05, -93.17],
            "country": "US",
            "center": [44.955, -93.275],
            "zoom": 10,
            "tagline": "The City of Lakes",
            "locale": "en-US",
        }
    }
    cities_file = tmp_path / "cities.json"
    cities_file.write_text(json.dumps(cities_data), encoding="utf-8")
    vis_root = tmp_path / "visualizer"
    vis_root.mkdir()

    with patch("transporte.extract.query_with_retry", return_value=fake_overpass):
        with patch.object(sys, "argv", [
            "extract-transporte",
            "--city", "minneapolis",
            "--cities-file", str(cities_file),
            "--visualizer-root", str(vis_root),
        ]):
            main()

    out_path = vis_root / "cities" / "minneapolis" / "datos_transporte.js"
    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8")
    assert "var DATA_TRANSPORT_LRT" in content
    assert "var DATA_TRANSPORT_BUS" in content
    assert "var DATA_TRANSPORT_COMMUTER" in content
    assert "var DATA_TRANSPORT_BRT" in content
    assert "METRO Green Line" in content
    assert "Route 5" in content
    manifest_path = vis_root / "cities" / "minneapolis" / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "transporte" in manifest["modules"]
    assert manifest["modules"]["transporte"]["features"] == 2
