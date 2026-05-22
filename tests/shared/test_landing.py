"""Tests del generador de landing (index.html)."""
import sys, os, json
from pathlib import Path
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from shared.landing import build_landing_html, _format_count


def _city_entry(name="Test", country="USA", tagline="t"):
    return {
        "display_name": name, "country": country,
        "bbox": [44.86, -93.38, 45.05, -93.17],
        "center": [44.97, -93.27], "zoom": 12,
        "tagline": tagline, "locale": "es"
    }


def test_landing_html_has_one_card_per_city():
    cities = {
        "minneapolis": _city_entry("Minneapolis, MN"),
        "manhattan": _city_entry("Manhattan, NYC"),
    }
    manifests = {
        "minneapolis": {"modules": {"zoning": {"hash": "a", "features": 100},
                                     "vial": {"hash": "b", "features": 200},
                                     "services": {"hash": "c", "features": 50}}},
        "manhattan": {"modules": {"zoning": {"hash": "d", "features": 500}}},
    }
    html = build_landing_html(cities, manifests)
    assert html.count('class="city-card"') == 2
    assert 'href="map.html?city=minneapolis"' in html
    assert 'href="map.html?city=manhattan"' in html
    assert "Minneapolis, MN" in html
    assert "Manhattan, NYC" in html


def test_landing_html_shows_module_badges():
    cities = {
        "minneapolis": _city_entry("Mpls"),
        "manhattan": _city_entry("Man"),
    }
    manifests = {
        "minneapolis": {"modules": {"zoning": {"hash":"a","features":1},
                                     "vial": {"hash":"b","features":1},
                                     "services": {"hash":"c","features":1}}},
        "manhattan": {"modules": {"zoning": {"hash":"d","features":1}}},
    }
    html = build_landing_html(cities, manifests)
    mpls_section = html[html.index("Mpls"):html.index("Man")]
    assert "Zoning" in mpls_section
    assert "Vial" in mpls_section
    assert "Servicios" in mpls_section
    man_section = html[html.index("Man"):]
    assert "Zoning" in man_section
    assert "Vial" not in man_section
    assert "Servicios" not in man_section


def test_landing_html_shows_feature_counts():
    cities = {"madison": _city_entry("Madison")}
    manifests = {"madison": {"modules": {"zoning": {"hash":"x","features":12345}}}}
    html = build_landing_html(cities, manifests)
    assert "12.3k" in html  # _format_count humaniza 12345 → 12.3k


def test_landing_html_handles_city_without_manifest():
    """Ciudad en registro pero sin manifest (ej. recién agregada, no extraída aún)."""
    cities = {"future_city": _city_entry("Future")}
    manifests = {}
    html = build_landing_html(cities, manifests)
    assert "Future" in html
    assert "Sin datos" in html or "pending" in html.lower()


def test_landing_html_includes_request_city_cta():
    cities = {"madison": _city_entry("Madison")}
    manifests = {"madison": {"modules": {"zoning": {"hash":"x","features":1}}}}
    html = build_landing_html(cities, manifests)
    assert "city-request" in html.lower() or "request" in html.lower()
    assert "github.com" in html.lower() or "issues/new" in html.lower()


def test_format_count_small_numbers():
    assert _format_count(0) == "0"
    assert _format_count(1) == "1"
    assert _format_count(999) == "999"


def test_format_count_thousands():
    assert _format_count(1000) == "1.0k"
    assert _format_count(12345) == "12.3k"
    assert _format_count(999999) == "1000.0k"  # boundary edge


def test_format_count_millions():
    assert _format_count(1_000_000) == "1.0M"
    assert _format_count(1_500_000) == "1.5M"


def test_format_count_handles_negative_defensively():
    # Negative shouldn't happen but defensive guard ensures sane output
    assert _format_count(-50) == "0"
    assert _format_count(-1000) == "0"


def test_cities_json_has_country_code_for_all_cities():
    """Every city in cities.json must have a valid ISO 3166-1 alpha-2 country_code."""
    import json
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[2]
    cities = json.loads((repo_root / "cities.json").read_text(encoding="utf-8"))
    for slug, entry in cities.items():
        assert "country_code" in entry, f"Missing country_code in {slug}"
        code = entry["country_code"]
        assert isinstance(code, str), f"{slug}: country_code must be string"
        assert len(code) == 2, f"{slug}: country_code must be 2 chars, got {code!r}"
        assert code.isupper() and code.isalpha(), f"{slug}: country_code must be uppercase letters, got {code!r}"
