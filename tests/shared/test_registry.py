"""Tests del registro de ciudades (cities.json) y manifest per-city."""
import sys, os, json
import pytest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from shared.registry import (
    load_cities, get_city, CityNotFoundError, RegistryError,
    load_manifest, save_manifest_entry, manifest_path, hash_file, VALID_MODULES,
)


def _valid_entry():
    return {
        "display_name": "Test City",
        "country": "USA",
        "bbox": [44.86, -93.38, 45.05, -93.17],
        "center": [44.97, -93.27],
        "zoom": 12,
        "tagline": "test",
        "locale": "es",
    }


def test_load_cities_reads_valid_json(tmp_path):
    p = tmp_path / "cities.json"
    p.write_text(json.dumps({"minneapolis": _valid_entry()}))
    cities = load_cities(p)
    assert "minneapolis" in cities
    assert cities["minneapolis"]["bbox"] == [44.86, -93.38, 45.05, -93.17]


def test_load_cities_missing_file_raises(tmp_path):
    with pytest.raises(RegistryError, match="no existe"):
        load_cities(tmp_path / "missing.json")


def test_load_cities_malformed_json_raises(tmp_path):
    p = tmp_path / "cities.json"
    p.write_text("not json {")
    with pytest.raises(RegistryError, match="JSON"):
        load_cities(p)


def test_load_cities_missing_required_field_raises(tmp_path):
    p = tmp_path / "cities.json"
    broken = {"display_name": "X"}  # missing bbox, center, etc.
    p.write_text(json.dumps({"broken": broken}))
    with pytest.raises(RegistryError, match="bbox"):
        load_cities(p)


def test_load_cities_invalid_bbox_shape_raises(tmp_path):
    p = tmp_path / "cities.json"
    e = _valid_entry()
    e["bbox"] = [44.86, -93.38, 45.05]  # 3 floats instead of 4
    p.write_text(json.dumps({"broken": e}))
    with pytest.raises(RegistryError, match="4 floats"):
        load_cities(p)


def test_load_cities_inverted_bbox_raises(tmp_path):
    p = tmp_path / "cities.json"
    e = _valid_entry()
    e["bbox"] = [45.05, -93.17, 44.86, -93.38]  # south > north
    p.write_text(json.dumps({"broken": e}))
    with pytest.raises(RegistryError, match="south>=north"):
        load_cities(p)


def test_get_city_returns_entry():
    cities = {"madison": _valid_entry()}
    c = get_city(cities, "madison")
    assert c["display_name"] == "Test City"


def test_get_city_unknown_raises():
    cities = {"madison": _valid_entry()}
    with pytest.raises(CityNotFoundError, match="atlantis"):
        get_city(cities, "atlantis")


def test_real_cities_json_loads_with_5_entries():
    """Regression test: el cities.json del repo debe tener exactamente 5 entries válidas."""
    repo_root = Path(__file__).resolve().parents[2]
    p = repo_root / "cities.json"
    cities = load_cities(p)
    expected = {"minneapolis", "manhattan", "tokyo", "amsterdam", "madison"}
    assert set(cities.keys()) == expected, f"Esperaba {expected}, got {set(cities.keys())}"


def test_real_cities_json_minneapolis_bbox_unchanged():
    """Regression: el bbox histórico de Mpls no debe cambiar (rompería prebuilts viejos)."""
    repo_root = Path(__file__).resolve().parents[2]
    cities = load_cities(repo_root / "cities.json")
    assert cities["minneapolis"]["bbox"] == [44.86, -93.38, 45.05, -93.17]


def test_manifest_path_structure(tmp_path):
    p = manifest_path(tmp_path, "manhattan")
    assert p == tmp_path / "cities" / "manhattan" / "manifest.json"


def test_load_manifest_returns_none_if_missing(tmp_path):
    assert load_manifest(tmp_path, "ghost") is None


def test_load_manifest_reads_valid(tmp_path):
    p = manifest_path(tmp_path, "manhattan")
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({
        "modules": {"zoning": {"hash": "abc123", "features": 100}},
        "generated_at": "2026-05-17T00:00:00+00:00",
    }))
    m = load_manifest(tmp_path, "manhattan")
    assert m["modules"]["zoning"]["features"] == 100


def test_load_manifest_malformed_raises(tmp_path):
    p = manifest_path(tmp_path, "manhattan")
    p.parent.mkdir(parents=True)
    p.write_text("not json")
    with pytest.raises(RegistryError, match="malformado"):
        load_manifest(tmp_path, "manhattan")


def test_save_manifest_entry_creates_file(tmp_path):
    data_file = tmp_path / "fake_data.js"
    data_file.write_text("const X = 1;")
    manifest = save_manifest_entry(tmp_path, "manhattan", "zoning", data_file, 42)
    assert manifest["modules"]["zoning"]["features"] == 42
    assert len(manifest["modules"]["zoning"]["hash"]) == 8
    assert manifest["modules"]["zoning"]["hash"] == hash_file(data_file)
    assert "generated_at" in manifest
    on_disk = load_manifest(tmp_path, "manhattan")
    assert on_disk == manifest


def test_save_manifest_entry_preserves_other_modules(tmp_path):
    p = manifest_path(tmp_path, "minneapolis")
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({
        "modules": {"zoning": {"hash": "old", "features": 1}},
        "generated_at": "2026-05-01T00:00:00+00:00",
    }))
    data_file = tmp_path / "fake_vial.js"
    data_file.write_text("const Y = 2;")
    manifest = save_manifest_entry(tmp_path, "minneapolis", "vial", data_file, 99)
    assert "zoning" in manifest["modules"]
    assert "vial" in manifest["modules"]
    assert manifest["modules"]["zoning"]["features"] == 1
    assert manifest["modules"]["vial"]["features"] == 99


def test_save_manifest_entry_invalid_module_raises(tmp_path):
    data_file = tmp_path / "x.js"
    data_file.write_text("x")
    with pytest.raises(ValueError, match="módulo"):
        save_manifest_entry(tmp_path, "x", "invalid_module", data_file, 1)


def test_hash_file_deterministic(tmp_path):
    p = tmp_path / "f.js"
    p.write_text("hello")
    h1 = hash_file(p)
    h2 = hash_file(p)
    assert h1 == h2
    assert len(h1) == 8
