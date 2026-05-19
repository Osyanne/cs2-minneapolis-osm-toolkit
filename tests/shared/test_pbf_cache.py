"""Tests for shared.pbf_cache."""
from __future__ import annotations

import pytest

from shared.pbf_cache import geofabrik_url, GeofabrikRegionError


class TestGeofabrikUrl:
    def test_us_state(self):
        url = geofabrik_url("north-america/us/minnesota")
        assert url == "https://download.geofabrik.de/north-america/us/minnesota-latest.osm.pbf"

    def test_country(self):
        url = geofabrik_url("europe/netherlands")
        assert url == "https://download.geofabrik.de/europe/netherlands-latest.osm.pbf"

    def test_strips_leading_slash(self):
        url = geofabrik_url("/europe/romania")
        assert url == "https://download.geofabrik.de/europe/romania-latest.osm.pbf"

    def test_strips_pbf_suffix_if_present(self):
        url = geofabrik_url("europe/germany-latest.osm.pbf")
        assert url == "https://download.geofabrik.de/europe/germany-latest.osm.pbf"

    def test_empty_region_raises(self):
        with pytest.raises(GeofabrikRegionError):
            geofabrik_url("")

    def test_none_region_raises(self):
        with pytest.raises(GeofabrikRegionError):
            geofabrik_url(None)  # type: ignore[arg-type]


import time
from pathlib import Path
from unittest.mock import patch, MagicMock

from shared.pbf_cache import ensure_pbf, is_fresh, DEFAULT_TTL_SECONDS


class TestIsFresh:
    def test_missing_file_not_fresh(self, tmp_path: Path):
        assert is_fresh(tmp_path / "nope.pbf", ttl_seconds=86400) is False

    def test_recent_file_is_fresh(self, tmp_path: Path):
        f = tmp_path / "recent.pbf"
        f.write_bytes(b"x")
        assert is_fresh(f, ttl_seconds=86400) is True

    def test_old_file_not_fresh(self, tmp_path: Path):
        f = tmp_path / "old.pbf"
        f.write_bytes(b"x")
        # Set mtime to 8 days ago
        old = time.time() - (8 * 86400)
        import os
        os.utime(f, (old, old))
        assert is_fresh(f, ttl_seconds=7 * 86400) is False


class TestEnsurePbf:
    def test_uses_cached_when_fresh(self, tmp_path: Path):
        cache_dir = tmp_path / "pbfs"
        cache_dir.mkdir()
        cached = cache_dir / "europe-netherlands-latest.osm.pbf"
        cached.write_bytes(b"fake pbf content")

        with patch("shared.pbf_cache.requests.get") as mock_get:
            result = ensure_pbf("europe/netherlands", cache_dir=cache_dir)

        assert result == cached
        mock_get.assert_not_called()

    def test_downloads_when_missing(self, tmp_path: Path):
        cache_dir = tmp_path / "pbfs"

        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"fake ", b"pbf ", b"data"]
        mock_response.headers = {"content-length": "13"}
        mock_response.raise_for_status = MagicMock()

        with patch("shared.pbf_cache.requests.get", return_value=mock_response) as mock_get:
            result = ensure_pbf("europe/netherlands", cache_dir=cache_dir)

        assert result.exists()
        assert result.read_bytes() == b"fake pbf data"
        assert mock_get.call_count == 1
        args, _ = mock_get.call_args
        assert "europe/netherlands-latest.osm.pbf" in args[0]

    def test_force_refresh_redownloads(self, tmp_path: Path):
        cache_dir = tmp_path / "pbfs"
        cache_dir.mkdir()
        cached = cache_dir / "europe-netherlands-latest.osm.pbf"
        cached.write_bytes(b"old content")

        mock_response = MagicMock()
        mock_response.iter_content.return_value = [b"new content"]
        mock_response.headers = {"content-length": "11"}
        mock_response.raise_for_status = MagicMock()

        with patch("shared.pbf_cache.requests.get", return_value=mock_response):
            result = ensure_pbf(
                "europe/netherlands",
                cache_dir=cache_dir,
                force_refresh=True,
            )

        assert result.read_bytes() == b"new content"
