"""Tests del generador de landing (index.html)."""
import sys, os, json
from pathlib import Path
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from shared.landing import build_landing_html, _format_count


def _city_entry(name="Test", country="USA", tagline="t", country_code="US"):
    return {
        "display_name": name, "country": country,
        "country_code": country_code,
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
    # Count only city cards (not the request-city card which uses class="card request")
    # The substring 'class="card"' (with closing quote) doesn't match 'class="card request"'.
    assert html.count('class="card"') == 2
    assert 'href="map.html?city=minneapolis"' in html
    assert 'href="map.html?city=manhattan"' in html
    assert "Minneapolis, MN" in html
    assert "Manhattan, NYC" in html


def test_landing_html_shows_module_dots():
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
    # All 3 modules → 3 "on" dots, 0 "off"
    assert mpls_section.count('class="mod"') == 3
    assert "mod off" not in mpls_section

    man_section = html[html.index("Man"):]
    # Only zoning → 1 "on", 2 "off"
    # (request-card and footer don't contain .mod elements, so counts are clean)
    assert man_section.count('class="mod"') == 1
    assert man_section.count("mod off") == 2


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
    # Pending state in new design = all 3 dots off + count "0"
    future_section = html[html.index("Future"):]
    assert future_section.count("mod off") == 3


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


def test_country_to_flag_usa():
    from shared.landing import country_to_flag
    assert country_to_flag("US") == "🇺🇸"


def test_country_to_flag_lowercase_normalized():
    from shared.landing import country_to_flag
    assert country_to_flag("us") == "🇺🇸"


def test_country_to_flag_netherlands():
    from shared.landing import country_to_flag
    assert country_to_flag("NL") == "🇳🇱"


def test_country_to_flag_empty_returns_empty():
    from shared.landing import country_to_flag
    assert country_to_flag("") == ""
    assert country_to_flag(None) == ""


def test_region_counts_basic():
    from shared.landing import region_counts
    cities = {
        "a": {"country": "USA", "display_name": "A", "tagline": "", "bbox":[0,0,0,0],"center":[0,0],"zoom":12,"locale":"es"},
        "b": {"country": "Netherlands", "display_name": "B", "tagline": "", "bbox":[0,0,0,0],"center":[0,0],"zoom":12,"locale":"es"},
        "c": {"country": "USA", "display_name": "C", "tagline": "", "bbox":[0,0,0,0],"center":[0,0],"zoom":12,"locale":"es"},
        "d": {"country": "Brazil", "display_name": "D", "tagline": "", "bbox":[0,0,0,0],"center":[0,0],"zoom":12,"locale":"es"},
    }
    counts = region_counts(cities)
    assert counts["all"] == 4
    assert counts["north-america"] == 2
    assert counts["europe"] == 1
    assert counts["south-america"] == 1


def test_region_counts_unknown_country_goes_to_other():
    from shared.landing import region_counts
    cities = {
        "x": {"country": "Atlantis", "display_name": "X", "tagline": "", "bbox":[0,0,0,0],"center":[0,0],"zoom":12,"locale":"es"},
    }
    counts = region_counts(cities)
    assert counts["all"] == 1
    assert counts.get("other", 0) == 1


def test_country_to_region_known_countries():
    from shared.landing import COUNTRY_TO_REGION
    assert COUNTRY_TO_REGION["USA"] == "north-america"
    assert COUNTRY_TO_REGION["Netherlands"] == "europe"
    assert COUNTRY_TO_REGION["Brazil"] == "south-america"
    assert COUNTRY_TO_REGION["Norway"] == "europe"
    assert COUNTRY_TO_REGION["Romania"] == "europe"


def test_build_stats_basic_counts():
    from shared.landing import build_stats
    cities = {
        "a": {"country": "USA", "display_name": "A", "tagline": "", "country_code": "US", "bbox":[0,0,0,0],"center":[0,0],"zoom":12,"locale":"es"},
        "b": {"country": "Netherlands", "display_name": "B", "tagline": "", "country_code": "NL", "bbox":[0,0,0,0],"center":[0,0],"zoom":12,"locale":"es"},
        "c": {"country": "USA", "display_name": "C", "tagline": "", "country_code": "US", "bbox":[0,0,0,0],"center":[0,0],"zoom":12,"locale":"es"},
    }
    manifests = {
        "a": {"modules": {"zoning": {"features": 100}, "vial": {"features": 50}}},
        "b": {"modules": {"zoning": {"features": 200}}},
        "c": {"modules": {"zoning": {"features": 1000}}},
    }
    stats = build_stats(cities, manifests)
    assert stats["cities_count"] == 3
    assert stats["features_total"] == "1.4k"  # 100+50+200+1000 = 1350 → 1.4k via _format_count
    assert stats["countries_count"] == 2  # USA + Netherlands


def test_build_stats_handles_missing_manifest():
    from shared.landing import build_stats
    cities = {
        "a": {"country": "USA", "display_name": "A", "tagline": "", "country_code": "US", "bbox":[0,0,0,0],"center":[0,0],"zoom":12,"locale":"es"},
    }
    manifests = {}  # missing entirely
    stats = build_stats(cities, manifests)
    assert stats["cities_count"] == 1
    assert stats["features_total"] == "0"
    assert stats["countries_count"] == 1


def test_build_stats_includes_version():
    from shared.landing import build_stats
    cities = {"a": {"country": "USA", "display_name": "A", "tagline": "", "country_code": "US", "bbox":[0,0,0,0],"center":[0,0],"zoom":12,"locale":"es"}}
    manifests = {}
    stats = build_stats(cities, manifests)
    assert "version" in stats
    assert stats["version"].startswith("v")
    assert "." in stats["version"]  # like "v3.4"


def test_card_html_has_lazy_loaded_img():
    from shared.landing import _card_html
    entry = _city_entry("Minneapolis, MN", "USA", "tag", "US")
    manifest = {"modules": {"zoning": {"features": 100}}}
    html = _card_html("minneapolis", entry, manifest)
    assert '<img' in html
    assert 'loading="lazy"' in html
    assert 'src="assets/thumbnails/minneapolis.png"' in html
    assert 'alt=' in html


def test_card_html_has_data_region_and_data_search():
    from shared.landing import _card_html
    entry = _city_entry("Minneapolis, MN", "USA", "Ciudad hero", "US")
    manifest = {"modules": {"zoning": {"features": 100}}}
    html = _card_html("minneapolis", entry, manifest)
    assert 'data-region="north-america"' in html
    assert 'data-search="' in html
    assert "ciudad hero" in html.lower()


def test_card_html_has_flag_emoji():
    from shared.landing import _card_html
    entry = _city_entry("Amsterdam", "Netherlands", "tag", "NL")
    manifest = {"modules": {"zoning": {"features": 100}}}
    html = _card_html("amsterdam", entry, manifest)
    assert "🇳🇱" in html


def test_card_html_module_dots_reflect_available_modules():
    from shared.landing import _card_html
    entry = _city_entry("M", "USA", "t", "US")

    # All 3 modules present → 3 "on" dots, 0 "off"
    manifest_full = {"modules": {"zoning": {"features": 1}, "vial": {"features": 1}, "services": {"features": 1}}}
    html_full = _card_html("m", entry, manifest_full)
    assert html_full.count('class="mod"') == 3  # substring matches ONLY on-dots (off has 'class="mod off"')
    assert "mod off" not in html_full

    # Only zoning → 1 "on", 2 "off"
    manifest_partial = {"modules": {"zoning": {"features": 1}}}
    html_partial = _card_html("m", entry, manifest_partial)
    assert html_partial.count('class="mod"') == 1
    assert html_partial.count("mod off") == 2


def test_card_html_missing_manifest_shows_pending_state():
    from shared.landing import _card_html
    entry = _city_entry("Future", "USA", "t", "US")
    html = _card_html("future", entry, None)
    assert "future" in html.lower()
    assert html.count("mod off") == 3
    assert "0" in html or "—" in html


def test_card_html_handles_missing_country_code_gracefully():
    """Old cities.json entries without country_code should still render (no flag)."""
    from shared.landing import _card_html
    entry = {
        "display_name": "Old City", "country": "USA",
        "bbox": [0,0,0,0], "center": [0,0], "zoom": 12,
        "tagline": "t", "locale": "es"
        # No country_code
    }
    manifest = {"modules": {"zoning": {"features": 100}}}
    html = _card_html("old_city", entry, manifest)
    assert "Old City" in html


def test_landing_html_links_external_stylesheet():
    cities = {"minneapolis": _city_entry("M")}
    manifests = {"minneapolis": {"modules": {"zoning": {"features": 1}}}}
    html = build_landing_html(cities, manifests)
    assert 'href="assets/landing.css"' in html
    assert '<style' not in html  # No inline styles


def test_landing_html_has_header_with_brand_and_version():
    cities = {"m": _city_entry("M")}
    manifests = {"m": {"modules": {"zoning": {"features": 1}}}}
    html = build_landing_html(cities, manifests)
    assert "CS2 OSM Toolkit" in html
    # Version tag from pyproject (v3.4 or similar)
    assert "v3.4" in html or "v3.5" in html


def test_landing_html_has_hero_with_headline_and_ctas():
    cities = {"m": _city_entry("M")}
    manifests = {"m": {"modules": {"zoning": {"features": 1}}}}
    html = build_landing_html(cities, manifests)
    assert '<h1' in html
    assert "Cities: Skylines 2" in html
    assert 'href="#gallery"' in html  # primary CTA anchor


def test_landing_html_has_stats_banner_with_4_stats():
    cities = {
        "a": _city_entry("A", "USA", "t", "US"),
        "b": _city_entry("B", "Netherlands", "t", "NL"),
        "c": _city_entry("C", "Brazil", "t", "BR"),
    }
    manifests = {
        "a": {"modules": {"zoning": {"features": 100}}},
        "b": {"modules": {"zoning": {"features": 200}}},
        "c": {"modules": {"zoning": {"features": 300}}},
    }
    html = build_landing_html(cities, manifests)
    assert 'class="stats"' in html
    # Total features 600 → "600"
    assert "600" in html
    # Version
    assert "v3.4" in html or "v3.5" in html


def test_landing_html_has_filter_pills():
    cities = {
        "a": _city_entry("A", "USA", "t", "US"),
        "b": _city_entry("B", "Netherlands", "t", "NL"),
    }
    manifests = {"a": {"modules": {"zoning": {"features": 1}}},
                 "b": {"modules": {"zoning": {"features": 1}}}}
    html = build_landing_html(cities, manifests)
    assert 'data-region="all"' in html
    assert 'data-region="north-america"' in html
    assert 'data-region="europe"' in html
    assert "All" in html
    assert "North America" in html
    assert "Europe" in html


def test_landing_html_has_search_input():
    cities = {"m": _city_entry("M")}
    manifests = {"m": {"modules": {"zoning": {"features": 1}}}}
    html = build_landing_html(cities, manifests)
    assert '<input' in html
    assert 'id="search"' in html
    assert 'type="search"' in html


def test_landing_html_has_request_city_card():
    cities = {"m": _city_entry("M")}
    manifests = {"m": {"modules": {"zoning": {"features": 1}}}}
    html = build_landing_html(cities, manifests)
    assert 'class="card request"' in html
    assert "Request your city" in html
    assert "issues/new" in html


def test_landing_html_has_empty_state_hidden_by_default():
    cities = {"m": _city_entry("M")}
    manifests = {"m": {"modules": {"zoning": {"features": 1}}}}
    html = build_landing_html(cities, manifests)
    assert 'class="empty-state"' in html
    assert "No cities match" in html


def test_landing_html_has_footer_with_patreon_link():
    cities = {"m": _city_entry("M")}
    manifests = {"m": {"modules": {"zoning": {"features": 1}}}}
    html = build_landing_html(cities, manifests)
    assert '<footer' in html
    assert "patreon" in html.lower()


def test_landing_html_includes_filter_javascript():
    cities = {"m": _city_entry("M")}
    manifests = {"m": {"modules": {"zoning": {"features": 1}}}}
    html = build_landing_html(cities, manifests)
    assert '<script' in html
    assert "addEventListener" in html
