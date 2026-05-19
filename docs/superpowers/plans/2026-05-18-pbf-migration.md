# PBF Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Overpass API extraction with local `.osm.pbf` extraction (Geofabrik regional dumps via `pyrosm`), preserving the existing Overpass-shape JSON contract so consumer code in `zoning/`, `vial/`, and `services/` is unchanged.

**Architecture:** Adapter pattern. New `shared/pbf_client.py` exposes the same `query_with_retry(query, label) -> dict` signature as `shared/overpass_client.py` but reads from a cached regional PBF and re-emits results in Overpass-compatible shape. Each `zones.py` adds a `build_pbf_filters(bbox)` sibling next to `build_queries(bbox)` returning structured filter specs. Each `extract*.py` imports from `pbf_client` instead of `overpass_client`, with the old client kept as fallback under a `--source=overpass` CLI flag for one minor version (deprecate in v3.5.0, remove in v4.0.0).

**Tech Stack:**
- `pyosmium>=3.7.0` — Official OSM Python binding to libosmium (C++). Handler-based API, returns native osmium objects. Wheels available for Python 3.11–3.14.
- `shapely>=2.0.0` — already in deps, geometry ops (parses WKB from pyosmium's WKBFactory)
- `requests>=2.31.0` — already in deps, used for Geofabrik downloads
- `pytest>=7.0.0` — already in deps
- Geofabrik download URLs — https://download.geofabrik.de/

> **2026-05-18 plan revision:** Originally specified `pyrosm`. Pivoted to `pyosmium` because pyrosm's transitive dep `pyrobuf 0.9.3` uses a deprecated `distutils` API that fails on modern setuptools (project venv is Python 3.14). Tasks 4–7 (pbf_client implementation) use the pyosmium handler pattern instead of pyrosm's GeoDataFrame accessors — will be revised in detail when Phase 3 starts.
>
> **2026-05-18 dep resolution note:** `uv sync` resolved `osmium 4.3.1` (not 3.7.x). pyosmium had major API changes between 3.x and 4.x: use `osmium.handler.SimpleHandler` (not bare `osmium.SimpleHandler`), the new `osmium.FileProcessor` for filtering, and `osmium.geom.WKBFactory` is still available. Tasks 4–7 must target the 4.x API surface. See https://docs.osmcode.org/pyosmium/v4.x/ when implementing Phase 3.

---

## File Structure

**New files:**
- `src/shared/pbf_cache.py` — Geofabrik URL resolver + download/cache with TTL
- `src/shared/pbf_filters.py` — `FilterSpec`, `Clause`, `TagSpec` dataclasses + validators
- `src/shared/pbf_client.py` — Filter execution against PBF, returns Overpass-shape dict
- `tests/shared/test_pbf_cache.py` — Cache logic (mock HTTP)
- `tests/shared/test_pbf_filters.py` — Filter spec validation
- `tests/shared/test_pbf_client.py` — End-to-end against Vatican fixture
- `tests/fixtures/vatican-city-latest.osm.pbf` — Tiny fixture (~600KB) checked in
- `tests/fixtures/README.md` — How to refresh fixtures

**Modified files:**
- `src/pyproject.toml` — Add `pyrosm` dependency, bump to v3.4.0
- `src/shared/registry.py` — Validate optional `pbf_region` field on city entries
- `src/zoning/zones.py` — Add `build_pbf_filters(bbox) -> dict[str, FilterSpec]`
- `src/vial/zones.py` — Add `build_vial_pbf_filter(bbox) -> FilterSpec`
- `src/services/zones.py` — Add `build_services_pbf_filter(bbox) -> FilterSpec`
- `src/zoning/extract.py` — `--source` CLI flag, route to pbf_client or overpass_client
- `src/zoning/extract_google_buildings.py` — Same `--source` flag
- `src/vial/extract.py` — Same `--source` flag
- `src/services/extract.py` — Same `--source` flag
- `cities.json` — Add `pbf_region` field per city (e.g. `"north-america/us/minnesota"`)
- `README.md` — Document PBF workflow, prerequisites, storage notes
- `CHANGELOG.md` — v3.4.0 entry

**Working directory:** All paths below are relative to `C:\Users\osyanne\Documents\Claude\Projects\Proyecto mineapolis\cs2-minneapolis-zoning\`.

**Test execution:** All `pytest` commands run from `src/`:
```bash
cd src
uv run pytest <test_path> -v
```

---

## Phase 0: Setup

### Task 0: Baseline & dependency

**Files:**
- Modify: `src/pyproject.toml`
- Verify: existing tests pass before any changes

- [x] **Step 0.1: Run existing tests to capture baseline**

```bash
cd src
uv run pytest -v
```

Expected: All existing tests pass. Record the count (e.g. "42 passed"). If any fail before our changes, stop and report — we need a green baseline.

- [x] **Step 0.2: Add pyosmium to dependencies**

Modify `src/pyproject.toml`:

```toml
[project]
name = "cs2-osm-toolkit"
version = "3.4.0"
description = "GIS toolkit modular: extract OpenStreetMap data for Cities: Skylines 2"
requires-python = ">=3.11"
dependencies = [
    "requests>=2.31.0",
    "tqdm>=4.66.0",
    "shapely>=2.0.0",
    "s2sphere>=0.2.5",
    "osmium>=3.7.0",
]
```

Note: PyPI package name is `osmium` (the import name is also `osmium`). The library is officially called "pyosmium" but installs as `osmium`.

- [x] **Step 0.3: Install new dependency**

```bash
cd src
uv sync
```

Expected: `osmium` installs from a prebuilt wheel (it ships wheels for Python 3.11–3.14 on Windows/macOS/Linux).

- [x] **Step 0.4: Verify osmium imports**

```bash
cd src
uv run python -c "import osmium; print(osmium.__version__)"
```

Expected: prints a version `>=3.7.0`.

- [x] **Step 0.5: Commit**

```bash
git add src/pyproject.toml src/uv.lock
git commit -m "chore(deps): add pyosmium 3.7.0 for PBF extraction, bump to v3.4.0-dev"
```

---

## Phase 1: PBF cache & downloader

### Task 1: Geofabrik URL resolver + cache

**Files:**
- Create: `src/shared/pbf_cache.py`
- Test: `tests/shared/test_pbf_cache.py`

- [x] **Step 1.1: Create tests directory structure**

```bash
mkdir -p tests/shared tests/fixtures tests/integration
touch tests/shared/__init__.py
```

- [x] **Step 1.2: Write failing test for URL resolution**

Create `tests/shared/test_pbf_cache.py`:

```python
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
```

- [x] **Step 1.3: Run test, verify it fails**

```bash
cd src
uv run pytest ../tests/shared/test_pbf_cache.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'shared.pbf_cache'`.

- [x] **Step 1.4: Implement geofabrik_url**

Create `src/shared/pbf_cache.py`:

```python
"""
pbf_cache.py
============
Geofabrik PBF download & local cache with TTL.

Resuelve regiones (e.g. 'north-america/us/minnesota') a URLs de
download.geofabrik.de, descarga el .osm.pbf y lo cachea localmente.
Re-descarga si el archivo cacheado es más viejo que TTL (default 7 días).

Uso:
    from shared.pbf_cache import ensure_pbf
    path = ensure_pbf("north-america/us/minnesota")
    # path es Path al .osm.pbf local
"""

from __future__ import annotations

from pathlib import Path

GEOFABRIK_BASE = "https://download.geofabrik.de"


class GeofabrikRegionError(ValueError):
    """Región Geofabrik inválida o no resoluble."""


def geofabrik_url(region: str) -> str:
    """
    Resuelve un identificador de región Geofabrik a URL de descarga.

    Args:
        region: Path-style region, e.g. 'north-america/us/minnesota',
            'europe/netherlands'. Acepta con o sin prefijo '/' y con o
            sin suffix '-latest.osm.pbf'.

    Returns:
        URL completa al .osm.pbf más reciente.

    Raises:
        GeofabrikRegionError: si region es vacía o None.
    """
    if not region or not isinstance(region, str):
        raise GeofabrikRegionError(f"Región vacía o no-str: {region!r}")
    cleaned = region.strip().lstrip("/")
    if cleaned.endswith("-latest.osm.pbf"):
        return f"{GEOFABRIK_BASE}/{cleaned}"
    return f"{GEOFABRIK_BASE}/{cleaned}-latest.osm.pbf"
```

- [x] **Step 1.5: Run test, verify pass**

```bash
cd src
uv run pytest ../tests/shared/test_pbf_cache.py -v
```

Expected: 6 passed.

- [x] **Step 1.6: Write failing test for cache logic**

Append to `tests/shared/test_pbf_cache.py`:

```python
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
```

- [x] **Step 1.7: Run new tests, verify they fail**

```bash
cd src
uv run pytest ../tests/shared/test_pbf_cache.py -v
```

Expected: 3 PASS (URL tests), 6 FAIL (cache tests) with `ImportError: cannot import name 'ensure_pbf'`.

- [x] **Step 1.8: Implement cache logic**

Append to `src/shared/pbf_cache.py`:

```python
import time

import requests

DEFAULT_TTL_SECONDS = 7 * 86400  # 7 días
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "cs2-osm-toolkit" / "pbf"
DOWNLOAD_CHUNK_BYTES = 1024 * 1024  # 1 MiB


def _local_filename(region: str) -> str:
    """Convierte 'north-america/us/minnesota' a 'north-america-us-minnesota-latest.osm.pbf'."""
    cleaned = region.strip().lstrip("/")
    if cleaned.endswith("-latest.osm.pbf"):
        cleaned = cleaned[: -len("-latest.osm.pbf")]
    return cleaned.replace("/", "-") + "-latest.osm.pbf"


def is_fresh(path: Path, ttl_seconds: int) -> bool:
    """Returns True if path exists and was modified within ttl_seconds."""
    if not path.exists():
        return False
    age = time.time() - path.stat().st_mtime
    return age < ttl_seconds


def ensure_pbf(
    region: str,
    cache_dir: Path | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    force_refresh: bool = False,
) -> Path:
    """
    Garantiza que el .osm.pbf de `region` exista localmente y esté fresco.

    Args:
        region: Identificador Geofabrik, e.g. 'north-america/us/minnesota'.
        cache_dir: Dónde cachear. Default ~/.cache/cs2-osm-toolkit/pbf/.
        ttl_seconds: Si el archivo existe pero es más viejo que esto, re-descarga.
        force_refresh: Re-descarga incluso si está fresco.

    Returns:
        Path al .osm.pbf local.

    Raises:
        GeofabrikRegionError: si region es inválida.
        requests.HTTPError: si la descarga falla.
    """
    if cache_dir is None:
        cache_dir = DEFAULT_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)

    target = cache_dir / _local_filename(region)

    if not force_refresh and is_fresh(target, ttl_seconds):
        print(f"[pbf_cache] cache hit: {target.name}", flush=True)
        return target

    url = geofabrik_url(region)
    print(f"[pbf_cache] downloading {url} -> {target}", flush=True)

    tmp = target.with_suffix(target.suffix + ".part")
    response = requests.get(url, stream=True, timeout=60)
    response.raise_for_status()

    total_bytes = int(response.headers.get("content-length", 0))
    written = 0
    with tmp.open("wb") as f:
        for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_BYTES):
            if not chunk:
                continue
            f.write(chunk)
            written += len(chunk)
            if total_bytes:
                pct = 100 * written / total_bytes
                print(
                    f"\r[pbf_cache] {written // (1024*1024)} MiB / "
                    f"{total_bytes // (1024*1024)} MiB ({pct:.0f}%)",
                    end="",
                    flush=True,
                )

    if total_bytes:
        print(flush=True)
    tmp.replace(target)
    return target
```

- [x] **Step 1.9: Run all cache tests, verify pass**

```bash
cd src
uv run pytest ../tests/shared/test_pbf_cache.py -v
```

Expected: 9 passed.

- [x] **Step 1.10: Commit**

```bash
git add src/shared/pbf_cache.py tests/shared/__init__.py tests/shared/test_pbf_cache.py
git commit -m "feat(pbf): add Geofabrik downloader with TTL cache"
```

---

## Phase 2: Filter spec types

### Task 2: Define and validate filter specs

**Files:**
- Create: `src/shared/pbf_filters.py`
- Test: `tests/shared/test_pbf_filters.py`

- [x] **Step 2.1: Write failing tests for filter specs**

Create `tests/shared/test_pbf_filters.py`:

```python
"""Tests for shared.pbf_filters."""
from __future__ import annotations

import pytest

from shared.pbf_filters import (
    Clause,
    FilterSpec,
    SpatialJoin,
    TagMatcher,
    FilterSpecError,
)


class TestTagMatcher:
    def test_exact_match(self):
        m = TagMatcher({"building": "apartments"})
        assert m.matches({"building": "apartments"}) is True
        assert m.matches({"building": "house"}) is False
        assert m.matches({}) is False

    def test_presence_match(self):
        m = TagMatcher({"shop": True})
        assert m.matches({"shop": "supermarket"}) is True
        assert m.matches({"shop": ""}) is True  # presence only
        assert m.matches({"building": "yes"}) is False

    def test_one_of_match(self):
        m = TagMatcher({"amenity": ["school", "hospital"]})
        assert m.matches({"amenity": "school"}) is True
        assert m.matches({"amenity": "hospital"}) is True
        assert m.matches({"amenity": "restaurant"}) is False

    def test_multi_tag_all_required(self):
        m = TagMatcher({"building": "apartments", "levels": True})
        assert m.matches({"building": "apartments", "levels": "5"}) is True
        assert m.matches({"building": "apartments"}) is False  # missing 'levels'

    def test_empty_matcher_raises(self):
        with pytest.raises(FilterSpecError):
            TagMatcher({})


class TestClause:
    def test_minimal_clause(self):
        c = Clause(
            geom_types=["way"],
            tag_filters=[TagMatcher({"building": "apartments"})],
        )
        assert "way" in c.geom_types
        assert len(c.tag_filters) == 1

    def test_empty_geom_types_raises(self):
        with pytest.raises(FilterSpecError):
            Clause(geom_types=[], tag_filters=[TagMatcher({"x": "y"})])

    def test_invalid_geom_type_raises(self):
        with pytest.raises(FilterSpecError):
            Clause(geom_types=["polygon"], tag_filters=[TagMatcher({"x": "y"})])  # type: ignore

    def test_empty_filters_raises(self):
        with pytest.raises(FilterSpecError):
            Clause(geom_types=["way"], tag_filters=[])


class TestSpatialJoin:
    def test_basic(self):
        sj = SpatialJoin(anchor_clause="comm", target_clause="apt", buffer_m=5.0)
        assert sj.buffer_m == 5.0

    def test_negative_buffer_raises(self):
        with pytest.raises(FilterSpecError):
            SpatialJoin(anchor_clause="a", target_clause="b", buffer_m=-1.0)


class TestFilterSpec:
    def test_minimal_spec(self):
        spec = FilterSpec(
            clauses={
                "apartments": Clause(
                    geom_types=["way"],
                    tag_filters=[TagMatcher({"building": "apartments"})],
                ),
            },
        )
        assert "apartments" in spec.clauses

    def test_empty_clauses_raises(self):
        with pytest.raises(FilterSpecError):
            FilterSpec(clauses={})

    def test_spatial_join_unknown_clause_raises(self):
        with pytest.raises(FilterSpecError):
            FilterSpec(
                clauses={
                    "a": Clause(geom_types=["way"], tag_filters=[TagMatcher({"x": "y"})]),
                },
                spatial_joins=[SpatialJoin(anchor_clause="a", target_clause="ghost", buffer_m=5)],
            )
```

- [x] **Step 2.2: Run, verify fails**

```bash
cd src
uv run pytest ../tests/shared/test_pbf_filters.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [x] **Step 2.3: Implement filter spec types**

Create `src/shared/pbf_filters.py`:

```python
"""
pbf_filters.py
==============
Structured filter specs para extracción PBF. Reemplazan Overpass QL strings
con datos estructurados que el pbf_client puede ejecutar contra un .osm.pbf.

Vocabulario:
- TagMatcher: predicado sobre tags de un elemento OSM
- Clause: "una clause de la query" — qué geometrías + qué tag filters (OR de tag matchers)
- SpatialJoin: post-procesado "elementos de target_clause que estén a buffer_m
  metros o menos de algún elemento de anchor_clause"
- FilterSpec: query completa — múltiples clauses nombradas (union deduplicada
  por (type, id)) + spatial joins opcionales

Diseñado para ser sibling de las funciones build_queries(bbox) existentes:
build_pbf_filters(bbox) retorna dict[str, FilterSpec] con las mismas keys.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


GeomType = Literal["node", "way", "relation"]
VALID_GEOM_TYPES: set[str] = {"node", "way", "relation"}


class FilterSpecError(ValueError):
    """Filter spec inválido."""


@dataclass(frozen=True)
class TagMatcher:
    """
    Predicado sobre el dict de tags de un elemento OSM.

    Reglas:
    - {"key": "value"}        — tag key existe Y igual a value
    - {"key": True}           — tag key existe (cualquier valor, incl. "")
    - {"key": [v1, v2, ...]}  — tag key existe Y valor está en la lista
    - Múltiples keys en el mismo TagMatcher: TODAS deben cumplirse (AND)
    """
    spec: dict[str, str | bool | list[str]]

    def __post_init__(self) -> None:
        if not self.spec:
            raise FilterSpecError("TagMatcher.spec no puede estar vacío")

    def matches(self, tags: dict[str, str]) -> bool:
        for key, expected in self.spec.items():
            actual = tags.get(key)
            if actual is None:
                return False
            if expected is True:
                continue  # presence-only
            if isinstance(expected, list):
                if actual not in expected:
                    return False
            else:
                if actual != expected:
                    return False
        return True


@dataclass(frozen=True)
class Clause:
    """
    Una clause: qué tipos de geometría buscar + qué tag matchers aplicar (OR).

    Un elemento matchea la clause si:
    - su tipo está en geom_types, Y
    - al menos un TagMatcher en tag_filters retorna True para sus tags
    """
    geom_types: list[GeomType]
    tag_filters: list[TagMatcher]

    def __post_init__(self) -> None:
        if not self.geom_types:
            raise FilterSpecError("Clause.geom_types no puede estar vacío")
        for gt in self.geom_types:
            if gt not in VALID_GEOM_TYPES:
                raise FilterSpecError(f"geom_type inválido: {gt!r}")
        if not self.tag_filters:
            raise FilterSpecError("Clause.tag_filters no puede estar vacío")

    def matches(self, geom_type: str, tags: dict[str, str]) -> bool:
        if geom_type not in self.geom_types:
            return False
        return any(m.matches(tags) for m in self.tag_filters)


@dataclass(frozen=True)
class SpatialJoin:
    """
    Post-procesado: 'devolver solo elementos de target_clause que estén a
    buffer_m metros o menos de algún elemento de anchor_clause'.

    Replica el patrón Overpass `(nodes A)->.x; way(around.x:5);`.
    """
    anchor_clause: str
    target_clause: str
    buffer_m: float

    def __post_init__(self) -> None:
        if self.buffer_m < 0:
            raise FilterSpecError(f"buffer_m no puede ser negativo: {self.buffer_m}")
        if not self.anchor_clause or not self.target_clause:
            raise FilterSpecError("anchor_clause y target_clause son obligatorios")


@dataclass(frozen=True)
class FilterSpec:
    """
    Query completa: múltiples clauses nombradas (union deduplicada por
    (type, id)) + spatial joins opcionales aplicados post-extracción.
    """
    clauses: dict[str, Clause]
    spatial_joins: list[SpatialJoin] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.clauses:
            raise FilterSpecError("FilterSpec.clauses no puede estar vacío")
        clause_names = set(self.clauses.keys())
        for sj in self.spatial_joins:
            if sj.anchor_clause not in clause_names:
                raise FilterSpecError(
                    f"SpatialJoin.anchor_clause '{sj.anchor_clause}' no está en clauses"
                )
            if sj.target_clause not in clause_names:
                raise FilterSpecError(
                    f"SpatialJoin.target_clause '{sj.target_clause}' no está en clauses"
                )
```

- [x] **Step 2.4: Run, verify pass**

```bash
cd src
uv run pytest ../tests/shared/test_pbf_filters.py -v
```

Expected: 12 passed.

- [x] **Step 2.5: Commit**

```bash
git add src/shared/pbf_filters.py tests/shared/test_pbf_filters.py
git commit -m "feat(pbf): add structured filter spec types (TagMatcher, Clause, FilterSpec)"
```

---

## Phase 3: PBF client core

### Task 3: Vatican fixture for testing

**Files:**
- Create: `tests/fixtures/vatican-city-latest.osm.pbf` (downloaded, ~600KB)
- Create: `tests/fixtures/README.md`

- [ ] **Step 3.1: Download Vatican fixture**

```bash
cd tests/fixtures
curl -o vatican-city-latest.osm.pbf https://download.geofabrik.de/europe/vatican-city-latest.osm.pbf
ls -lh vatican-city-latest.osm.pbf
```

Expected: file size ~500KB–800KB. If Vatican isn't available, fall back to Liechtenstein (~3MB).

- [ ] **Step 3.2: Document fixture source**

Create `tests/fixtures/README.md`:

```markdown
# Test fixtures

## vatican-city-latest.osm.pbf

Smallest Geofabrik regional PBF (~600KB), used to test `shared.pbf_client`
end-to-end without large downloads in CI.

**Source:** https://download.geofabrik.de/europe/vatican-city-latest.osm.pbf

**Refresh:**
```bash
cd tests/fixtures
curl -o vatican-city-latest.osm.pbf https://download.geofabrik.de/europe/vatican-city-latest.osm.pbf
```

**Bbox (approx):** `[41.900, 12.444, 41.908, 12.459]`

Vatican has handful of buildings, amenities, and ways — enough to exercise
all filter spec branches.
```

- [ ] **Step 3.3: Commit fixture**

```bash
git add tests/fixtures/vatican-city-latest.osm.pbf tests/fixtures/README.md
git commit -m "test: add Vatican PBF fixture (~600KB) for pbf_client tests"
```

### Task 4: Tag matching engine for PBF rows

**Files:**
- Create: `src/shared/pbf_client.py` (initial scaffold)
- Test: `tests/shared/test_pbf_client.py`

- [ ] **Step 4.1: Write failing test for tag matching against pyrosm-shaped row**

Create `tests/shared/test_pbf_client.py`:

```python
"""Tests for shared.pbf_client."""
from __future__ import annotations

from pathlib import Path

import pytest

from shared.pbf_client import (
    _tags_from_pyrosm_row,
    _row_matches_clause,
)
from shared.pbf_filters import Clause, TagMatcher


VATICAN_PBF = Path(__file__).resolve().parents[1] / "fixtures" / "vatican-city-latest.osm.pbf"


class TestTagsFromPyrosmRow:
    def test_extracts_top_level_columns(self):
        row = {"building": "apartments", "name": "Casa A", "geometry": "POLYGON(...)"}
        tags = _tags_from_pyrosm_row(row)
        assert tags["building"] == "apartments"
        assert tags["name"] == "Casa A"
        assert "geometry" not in tags

    def test_merges_tags_column(self):
        row = {
            "building": "yes",
            "tags": {"levels": "3", "roof:shape": "flat"},
            "geometry": "...",
        }
        tags = _tags_from_pyrosm_row(row)
        assert tags["building"] == "yes"
        assert tags["levels"] == "3"
        assert tags["roof:shape"] == "flat"

    def test_skips_nan_and_none(self):
        import math
        row = {"building": "yes", "amenity": None, "shop": math.nan}
        tags = _tags_from_pyrosm_row(row)
        assert tags["building"] == "yes"
        assert "amenity" not in tags
        assert "shop" not in tags

    def test_empty_row(self):
        assert _tags_from_pyrosm_row({}) == {}


class TestRowMatchesClause:
    def test_matches(self):
        clause = Clause(geom_types=["way"], tag_filters=[TagMatcher({"building": "apartments"})])
        row = {"building": "apartments"}
        assert _row_matches_clause(row, "way", clause) is True

    def test_wrong_geom_type(self):
        clause = Clause(geom_types=["way"], tag_filters=[TagMatcher({"building": "apartments"})])
        row = {"building": "apartments"}
        assert _row_matches_clause(row, "node", clause) is False

    def test_no_tag_match(self):
        clause = Clause(geom_types=["way"], tag_filters=[TagMatcher({"building": "apartments"})])
        row = {"building": "house"}
        assert _row_matches_clause(row, "way", clause) is False
```

- [ ] **Step 4.2: Run, verify fails**

```bash
cd src
uv run pytest ../tests/shared/test_pbf_client.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4.3: Implement tag extraction and row matching**

Create `src/shared/pbf_client.py`:

```python
"""
pbf_client.py
=============
Cliente de extracción PBF con API compatible con overpass_client.

Lee un .osm.pbf con pyrosm, aplica FilterSpec, y re-emite resultados en
forma Overpass-compatible (dict con clave 'elements', cada elemento con
'type', 'id', 'tags', 'geometry'/'members'/'lat,lon').

Diseñado como drop-in replacement de overpass_client para los extractores
existentes: la única diferencia es que toma FilterSpec en vez de QL string.

Uso:
    from shared.pbf_client import query
    data = query(pbf_path, bbox, filter_spec, label="apartments")
    # data["elements"] es lista con shape Overpass

Conversión a Overpass shape:
- way:      {"type": "way", "id": N, "tags": {...}, "geometry": [{"lat": ..., "lon": ...}, ...]}
- node:     {"type": "node", "id": N, "tags": {...}, "lat": ..., "lon": ...}
- relation: {"type": "relation", "id": N, "tags": {...},
             "members": [{"role": "outer", "geometry": [{"lat", "lon"}, ...]}]}
  (solo el outer más grande, para matchear lo que extract.py.coords_from_relation usa)
"""

from __future__ import annotations

import math
from typing import Any

from shared.pbf_filters import Clause


def _is_nan(v: Any) -> bool:
    return isinstance(v, float) and math.isnan(v)


def _tags_from_pyrosm_row(row: dict[str, Any]) -> dict[str, str]:
    """
    Extrae el dict de tags de una fila pyrosm.

    pyrosm pone tags comunes como columnas top-level (building, amenity, ...)
    y el resto en una columna 'tags' (dict). Hay que combinar ambos y filtrar
    None/NaN.
    """
    tags: dict[str, str] = {}

    extra = row.get("tags")
    if isinstance(extra, dict):
        for k, v in extra.items():
            if v is None or _is_nan(v):
                continue
            tags[str(k)] = str(v)

    for k, v in row.items():
        if k in ("geometry", "tags", "id", "osm_id", "osmid", "version", "timestamp"):
            continue
        if v is None or _is_nan(v):
            continue
        tags[str(k)] = str(v)

    return tags


def _row_matches_clause(row: dict[str, Any], geom_type: str, clause: Clause) -> bool:
    """True si row + geom_type satisfacen la Clause."""
    if geom_type not in clause.geom_types:
        return False
    tags = _tags_from_pyrosm_row(row)
    return any(m.matches(tags) for m in clause.tag_filters)
```

- [ ] **Step 4.4: Run, verify pass**

```bash
cd src
uv run pytest ../tests/shared/test_pbf_client.py -v
```

Expected: 7 passed.

- [ ] **Step 4.5: Commit**

```bash
git add src/shared/pbf_client.py tests/shared/test_pbf_client.py
git commit -m "feat(pbf): add pyrosm row tag extraction and clause matching"
```

### Task 5: Geometry conversion to Overpass shape

**Files:**
- Modify: `src/shared/pbf_client.py`
- Modify: `tests/shared/test_pbf_client.py`

- [ ] **Step 5.1: Write failing tests for geometry conversion**

Append to `tests/shared/test_pbf_client.py`:

```python
from shapely.geometry import Point, Polygon, MultiPolygon, LineString

from shared.pbf_client import (
    _geometry_to_overpass_way,
    _geometry_to_overpass_node,
    _geometry_to_overpass_relation,
)


class TestGeometryToOverpassWay:
    def test_polygon(self):
        poly = Polygon([(12.45, 41.90), (12.46, 41.90), (12.46, 41.91), (12.45, 41.90)])
        geom = _geometry_to_overpass_way(poly)
        # lat,lon order (Overpass convention)
        assert geom[0] == {"lat": 41.90, "lon": 12.45}
        assert len(geom) == 4

    def test_linestring(self):
        ls = LineString([(12.45, 41.90), (12.46, 41.91)])
        geom = _geometry_to_overpass_way(ls)
        assert geom == [
            {"lat": 41.90, "lon": 12.45},
            {"lat": 41.91, "lon": 12.46},
        ]

    def test_invalid_geometry_returns_none(self):
        assert _geometry_to_overpass_way(Point(12.45, 41.90)) is None


class TestGeometryToOverpassNode:
    def test_point(self):
        p = Point(12.45, 41.90)
        assert _geometry_to_overpass_node(p) == (41.90, 12.45)

    def test_non_point_returns_none(self):
        assert _geometry_to_overpass_node(LineString([(0, 0), (1, 1)])) is None


class TestGeometryToOverpassRelation:
    def test_multipolygon_picks_largest_outer(self):
        small = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
        big = Polygon([(10, 10), (20, 10), (20, 20), (10, 20), (10, 10)])
        mp = MultiPolygon([small, big])
        members = _geometry_to_overpass_relation(mp)
        assert len(members) == 1
        assert members[0]["role"] == "outer"
        # Should be the big polygon (lat,lon order)
        coords_lon = [pt["lon"] for pt in members[0]["geometry"]]
        assert 10 in coords_lon or 20 in coords_lon

    def test_single_polygon(self):
        poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 0)])
        members = _geometry_to_overpass_relation(poly)
        assert len(members) == 1
        assert members[0]["role"] == "outer"

    def test_invalid_returns_empty_list(self):
        assert _geometry_to_overpass_relation(Point(0, 0)) == []
```

- [ ] **Step 5.2: Run, verify fails**

```bash
cd src
uv run pytest ../tests/shared/test_pbf_client.py -v
```

Expected: 7 PASS (existing), new tests FAIL with `ImportError`.

- [ ] **Step 5.3: Implement geometry conversions**

Append to `src/shared/pbf_client.py`:

```python
from shapely.geometry import (
    LineString,
    MultiPolygon,
    Point,
    Polygon,
)
from shapely.geometry.base import BaseGeometry


def _geometry_to_overpass_way(geom: BaseGeometry) -> list[dict[str, float]] | None:
    """
    Convierte un Polygon o LineString shapely a lista
    [{"lat": ..., "lon": ...}, ...] estilo Overpass `out geom`.

    pyrosm devuelve coords en (lon, lat); Overpass usa (lat, lon).
    Para Polygon, usa exterior ring.
    """
    if isinstance(geom, Polygon):
        coords = list(geom.exterior.coords)
    elif isinstance(geom, LineString):
        coords = list(geom.coords)
    elif isinstance(geom, MultiPolygon):
        largest = max(geom.geoms, key=lambda p: p.area)
        coords = list(largest.exterior.coords)
    else:
        return None
    return [{"lat": lat, "lon": lon} for lon, lat in coords]


def _geometry_to_overpass_node(geom: BaseGeometry) -> tuple[float, float] | None:
    """Devuelve (lat, lon) para un Point, None para otros."""
    if not isinstance(geom, Point):
        return None
    return (geom.y, geom.x)


def _geometry_to_overpass_relation(geom: BaseGeometry) -> list[dict[str, Any]]:
    """
    Convierte un Polygon o MultiPolygon a lista de members estilo Overpass.

    Para matchear lo que extract.py.coords_from_relation hace (toma el outer
    más grande), solo emitimos el outer más grande como un único member.
    Esto pierde fidelidad de multipolygons complejos pero matchea el contrato
    actual del consumer.
    """
    if isinstance(geom, MultiPolygon):
        largest = max(geom.geoms, key=lambda p: p.area)
        coords = list(largest.exterior.coords)
    elif isinstance(geom, Polygon):
        coords = list(geom.exterior.coords)
    else:
        return []
    return [{
        "role": "outer",
        "type": "way",
        "geometry": [{"lat": lat, "lon": lon} for lon, lat in coords],
    }]
```

- [ ] **Step 5.4: Run, verify pass**

```bash
cd src
uv run pytest ../tests/shared/test_pbf_client.py -v
```

Expected: 14 passed.

- [ ] **Step 5.5: Commit**

```bash
git add src/shared/pbf_client.py tests/shared/test_pbf_client.py
git commit -m "feat(pbf): add geometry-to-Overpass-shape converters"
```

### Task 6: Spatial join post-processor

**Files:**
- Modify: `src/shared/pbf_client.py`
- Modify: `tests/shared/test_pbf_client.py`

- [ ] **Step 6.1: Write failing test for spatial join**

Append to `tests/shared/test_pbf_client.py`:

```python
from shared.pbf_client import _apply_spatial_join
from shared.pbf_filters import SpatialJoin


class TestSpatialJoin:
    def test_keeps_targets_near_anchors(self):
        anchors = [
            {"type": "node", "id": 1, "lat": 41.900, "lon": 12.450, "tags": {"shop": "supermarket"}},
        ]
        # Target way with one coord within ~5m of anchor
        targets = [
            {
                "type": "way", "id": 100,
                "tags": {"building": "apartments"},
                "geometry": [
                    {"lat": 41.90003, "lon": 12.45003},  # ~5m from anchor
                    {"lat": 41.90010, "lon": 12.45010},
                    {"lat": 41.90020, "lon": 12.45020},
                    {"lat": 41.90003, "lon": 12.45003},
                ],
            },
        ]
        result = _apply_spatial_join(targets, anchors, buffer_m=10.0)
        assert len(result) == 1
        assert result[0]["id"] == 100

    def test_filters_targets_far_from_anchors(self):
        anchors = [
            {"type": "node", "id": 1, "lat": 41.900, "lon": 12.450, "tags": {}},
        ]
        targets = [
            {
                "type": "way", "id": 200,
                "tags": {},
                "geometry": [
                    {"lat": 42.000, "lon": 13.000},  # ~100km away
                    {"lat": 42.001, "lon": 13.001},
                    {"lat": 42.002, "lon": 13.002},
                    {"lat": 42.000, "lon": 13.000},
                ],
            },
        ]
        result = _apply_spatial_join(targets, anchors, buffer_m=5.0)
        assert result == []

    def test_empty_anchors_returns_empty(self):
        targets = [{"type": "way", "id": 1, "geometry": [{"lat": 0, "lon": 0}], "tags": {}}]
        assert _apply_spatial_join(targets, [], buffer_m=5.0) == []
```

- [ ] **Step 6.2: Run, verify fails**

```bash
cd src
uv run pytest ../tests/shared/test_pbf_client.py -v
```

Expected: 14 PASS, 3 FAIL with `ImportError`.

- [ ] **Step 6.3: Implement spatial join**

Append to `src/shared/pbf_client.py`:

```python
from shapely.geometry import Point as _ShapelyPoint
from shapely.strtree import STRtree


# Aproximación métrica: 1 grado de latitud ≈ 111,000 m. Para buffer en metros
# convertimos a grados con (buffer_m / 111000). Esto es aceptable para
# distancias pequeñas (<100m) y latitudes no polares.
DEG_PER_METER = 1.0 / 111000.0


def _element_to_shapely_points(el: dict[str, Any]) -> list[_ShapelyPoint]:
    """Convierte cualquier elemento Overpass-shape a lista de Points para STRtree."""
    if el["type"] == "node":
        return [_ShapelyPoint(el["lon"], el["lat"])]
    if el["type"] == "way":
        return [_ShapelyPoint(pt["lon"], pt["lat"]) for pt in el.get("geometry", [])]
    if el["type"] == "relation":
        pts: list[_ShapelyPoint] = []
        for m in el.get("members", []):
            for pt in m.get("geometry", []):
                pts.append(_ShapelyPoint(pt["lon"], pt["lat"]))
        return pts
    return []


def _apply_spatial_join(
    targets: list[dict[str, Any]],
    anchors: list[dict[str, Any]],
    buffer_m: float,
) -> list[dict[str, Any]]:
    """
    Devuelve targets que tienen al menos un punto a buffer_m metros o menos
    de algún punto anchor.

    Implementación: STRtree de puntos anchor, query por bbox + distance check.
    """
    if not anchors or not targets:
        return []

    anchor_points: list[_ShapelyPoint] = []
    for a in anchors:
        anchor_points.extend(_element_to_shapely_points(a))
    if not anchor_points:
        return []

    tree = STRtree(anchor_points)
    buffer_deg = buffer_m * DEG_PER_METER

    kept: list[dict[str, Any]] = []
    for t in targets:
        target_points = _element_to_shapely_points(t)
        matched = False
        for tp in target_points:
            # query returns indices of candidate anchors within bbox of tp.buffer
            candidates_idx = tree.query(tp.buffer(buffer_deg))
            for idx in candidates_idx:
                ap = anchor_points[idx]
                if tp.distance(ap) <= buffer_deg:
                    matched = True
                    break
            if matched:
                break
        if matched:
            kept.append(t)
    return kept
```

- [ ] **Step 6.4: Run, verify pass**

```bash
cd src
uv run pytest ../tests/shared/test_pbf_client.py -v
```

Expected: 17 passed.

- [ ] **Step 6.5: Commit**

```bash
git add src/shared/pbf_client.py tests/shared/test_pbf_client.py
git commit -m "feat(pbf): add spatial-join post-processor for around.X:N patterns"
```

### Task 7: Top-level query() function with Vatican integration test

**Files:**
- Modify: `src/shared/pbf_client.py`
- Modify: `tests/shared/test_pbf_client.py`

- [ ] **Step 7.1: Write failing integration test against Vatican fixture**

Append to `tests/shared/test_pbf_client.py`:

```python
from shared.pbf_client import query
from shared.pbf_filters import FilterSpec, Clause, TagMatcher


VATICAN_BBOX = (41.900, 12.444, 41.908, 12.459)  # south, west, north, east


@pytest.mark.skipif(not VATICAN_PBF.exists(), reason="Vatican fixture missing")
class TestQueryAgainstVatican:
    def test_returns_overpass_shape_dict(self):
        spec = FilterSpec(
            clauses={
                "buildings": Clause(
                    geom_types=["way"],
                    tag_filters=[TagMatcher({"building": True})],
                ),
            },
        )
        result = query(VATICAN_PBF, VATICAN_BBOX, spec, label="buildings")
        assert "elements" in result
        assert isinstance(result["elements"], list)
        # Vatican has at least a few buildings
        assert len(result["elements"]) > 0
        first = result["elements"][0]
        assert first["type"] in ("way", "relation")
        assert "id" in first
        assert "tags" in first

    def test_no_match_returns_empty_elements(self):
        spec = FilterSpec(
            clauses={
                "fake": Clause(
                    geom_types=["way"],
                    tag_filters=[TagMatcher({"building": "this_value_does_not_exist_anywhere"})],
                ),
            },
        )
        result = query(VATICAN_PBF, VATICAN_BBOX, spec, label="empty")
        assert result == {"elements": []}

    def test_dedup_by_type_and_id(self):
        # Two clauses that both match buildings — same element should appear once
        spec = FilterSpec(
            clauses={
                "a": Clause(
                    geom_types=["way"],
                    tag_filters=[TagMatcher({"building": True})],
                ),
                "b": Clause(
                    geom_types=["way"],
                    tag_filters=[TagMatcher({"building": True})],
                ),
            },
        )
        result = query(VATICAN_PBF, VATICAN_BBOX, spec, label="dedup")
        ids = [(el["type"], el["id"]) for el in result["elements"]]
        assert len(ids) == len(set(ids))
```

- [ ] **Step 7.2: Run, verify fails**

```bash
cd src
uv run pytest ../tests/shared/test_pbf_client.py -v
```

Expected: 17 PASS, 3 FAIL with `ImportError: cannot import name 'query'`.

- [ ] **Step 7.3: Implement top-level query()**

Append to `src/shared/pbf_client.py`:

```python
import time
from pathlib import Path

from pyrosm import OSM

from shared.pbf_filters import FilterSpec


# pyrosm exposes these as separate accessors per geom type
_PYROSM_GETTERS = {
    "node": "get_pois",          # nodes with tags (POIs)
    "way": "get_buildings",      # ways with building or other tags
    "relation": "get_boundaries",  # not used directly; multipolygons come back via get_*
}


def _extract_all_geom_types(
    osm: OSM,
    geom_types: set[str],
    label: str,
) -> dict[str, list[dict[str, Any]]]:
    """
    Extrae todos los elementos de los tipos geom_types desde el PBF, sin filtrar
    aún por tags. Retorna {"node": [rows], "way": [rows], "relation": [rows]}.

    pyrosm tiene accessors específicos pero conviene un fallback genérico
    para evitar quedarnos cortos. Usamos:
      - way + relation:  get_buildings(custom_filter=None) y get_landuse()...
        En la práctica el más útil para nuestros casos es osm._way_records
        después de cargarlos. Para v3.4.0 usamos la API pública por categoría
        + un fallback con _node_coordinates para nodes.

    Implementación pragmática:
      - way: getMultiplePOIs con custom_filter=None devuelve todos los ways
        que tengan algún tag relevante. Aceptamos eso y refiltramos en Python.
      - node: get_pois() devuelve nodes-con-tags + ways/relations representativos
        — filtramos por geom_type=='Point' antes de devolver.
      - relation: pyrosm trata multipolygons como ways en el output de
        get_buildings/get_landuse — los identificamos por id negativo (convención
        pyrosm para relations) y los reclasificamos como type='relation'.
    """
    out: dict[str, list[dict[str, Any]]] = {"node": [], "way": [], "relation": []}

    # Estrategia única: pedir TODO via custom_filter={'building': True, ...}
    # con un filter abierto y filtrar después. Para v3.4.0 usamos un approach
    # simple: pedir buildings + landuse + amenities + highway separadamente y
    # combinar. Esto cubre nuestras 4 source categorías.
    chunks: list = []
    for getter_name in ("get_buildings", "get_landuse", "get_pois", "get_network"):
        getter = getattr(osm, getter_name, None)
        if getter is None:
            continue
        try:
            if getter_name == "get_network":
                gdf = getter(network_type="all")
            else:
                gdf = getter()
        except Exception as e:
            print(f"        [pbf:{label}] {getter_name} skipped: {e}", flush=True)
            continue
        if gdf is None or len(gdf) == 0:
            continue
        chunks.append(gdf)

    if not chunks:
        return out

    import pandas as pd
    all_rows = pd.concat(chunks, ignore_index=True, sort=False)

    # Dedup por (osm_type, id) — pyrosm a veces devuelve el mismo elemento por
    # múltiples getters.
    if "osm_type" in all_rows.columns:
        all_rows = all_rows.drop_duplicates(subset=["osm_type", "id"], keep="first")
    elif "id" in all_rows.columns:
        all_rows = all_rows.drop_duplicates(subset=["id"], keep="first")

    for _, row in all_rows.iterrows():
        row_dict = row.to_dict()
        osm_type = row_dict.get("osm_type")
        geom = row_dict.get("geometry")

        if osm_type is None:
            # Inferir por geometría
            if isinstance(geom, Point):
                osm_type = "node"
            elif isinstance(geom, (Polygon, LineString)):
                osm_type = "way"
            elif isinstance(geom, MultiPolygon):
                osm_type = "relation"
            else:
                continue

        if osm_type not in geom_types:
            continue
        out[osm_type].append(row_dict)

    return out


def _build_overpass_element(
    row: dict[str, Any],
    geom_type: str,
) -> dict[str, Any] | None:
    """Convierte una fila pyrosm a un elemento Overpass-shape, o None si inválido."""
    geom = row.get("geometry")
    if geom is None:
        return None

    osm_id = row.get("id") or row.get("osm_id") or row.get("osmid")
    if osm_id is None:
        return None

    tags = _tags_from_pyrosm_row(row)
    base = {"type": geom_type, "id": int(osm_id), "tags": tags}

    if geom_type == "node":
        latlon = _geometry_to_overpass_node(geom)
        if latlon is None:
            return None
        lat, lon = latlon
        base["lat"] = lat
        base["lon"] = lon
        return base

    if geom_type == "way":
        way_geom = _geometry_to_overpass_way(geom)
        if not way_geom:
            return None
        base["geometry"] = way_geom
        return base

    if geom_type == "relation":
        members = _geometry_to_overpass_relation(geom)
        if not members:
            return None
        base["members"] = members
        return base

    return None


def query(
    pbf_path: Path,
    bbox: tuple[float, float, float, float],
    filter_spec: FilterSpec,
    label: str = "query",
) -> dict[str, Any]:
    """
    Ejecuta un FilterSpec contra un .osm.pbf y devuelve resultado Overpass-shape.

    Args:
        pbf_path: Path al .osm.pbf (debe existir; usar pbf_cache.ensure_pbf primero).
        bbox: (south, west, north, east) en grados decimales.
        filter_spec: Estructura con clauses + spatial_joins opcionales.
        label: Etiqueta para logs.

    Returns:
        {"elements": [...]} con shape Overpass.

    Raises:
        FileNotFoundError: si pbf_path no existe.
    """
    if not pbf_path.exists():
        raise FileNotFoundError(f"PBF no encontrado: {pbf_path}")

    print(f"        [pbf:{label}] loading {pbf_path.name} bbox={bbox}", flush=True)
    start = time.monotonic()

    south, west, north, east = bbox
    # pyrosm bounding_box es [minx, miny, maxx, maxy] = [west, south, east, north]
    osm = OSM(str(pbf_path), bounding_box=[west, south, east, north])

    # Determinar qué geom_types necesitamos
    needed_geom_types: set[str] = set()
    for clause in filter_spec.clauses.values():
        needed_geom_types.update(clause.geom_types)

    raw_by_geom = _extract_all_geom_types(osm, needed_geom_types, label)

    # Aplicar clauses y construir índice por nombre
    elements_by_clause: dict[str, list[dict[str, Any]]] = {
        name: [] for name in filter_spec.clauses
    }
    seen: set[tuple[str, int]] = set()
    all_elements: list[dict[str, Any]] = []

    for clause_name, clause in filter_spec.clauses.items():
        for gt in clause.geom_types:
            for row in raw_by_geom.get(gt, []):
                if not _row_matches_clause(row, gt, clause):
                    continue
                element = _build_overpass_element(row, gt)
                if element is None:
                    continue
                key = (element["type"], element["id"])
                elements_by_clause[clause_name].append(element)
                if key not in seen:
                    seen.add(key)
                    all_elements.append(element)

    # Spatial joins: FILTRAN target_clause in place
    for sj in filter_spec.spatial_joins:
        targets = elements_by_clause[sj.target_clause]
        anchors = elements_by_clause[sj.anchor_clause]
        kept_ids = {(e["type"], e["id"]) for e in _apply_spatial_join(targets, anchors, sj.buffer_m)}
        # Reemplazar all_elements: quitar targets que NO sobrevivieron al join
        all_elements = [
            e for e in all_elements
            if (e["type"], e["id"]) not in {(t["type"], t["id"]) for t in targets}
            or (e["type"], e["id"]) in kept_ids
        ]
        elements_by_clause[sj.target_clause] = [
            t for t in targets if (t["type"], t["id"]) in kept_ids
        ]

    elapsed = time.monotonic() - start
    print(
        f"        [pbf:{label}] OK {len(all_elements)} elementos en {elapsed:.1f}s",
        flush=True,
    )
    return {"elements": all_elements}


def query_with_retry(
    pbf_path: Path,
    bbox: tuple[float, float, float, float],
    filter_spec: FilterSpec,
    label: str = "query",
) -> dict[str, Any]:
    """
    Drop-in compatibility shim que matchea la signature de
    overpass_client.query_with_retry pero opera sobre PBF local.

    No tiene "retry" real porque PBF local no falla por red — solo levanta
    FileNotFoundError si el archivo no existe (caller debe haber llamado
    pbf_cache.ensure_pbf antes).
    """
    return query(pbf_path, bbox, filter_spec, label)
```

- [ ] **Step 7.4: Run, verify pass**

```bash
cd src
uv run pytest ../tests/shared/test_pbf_client.py -v
```

Expected: 20 passed. If Vatican fixture is missing, those 3 tests skip — fix by re-downloading per Task 3.

- [ ] **Step 7.5: Commit**

```bash
git add src/shared/pbf_client.py tests/shared/test_pbf_client.py
git commit -m "feat(pbf): implement query() with pyrosm + Overpass-shape output"
```

---

## Phase 4: Per-module migration

### Task 8: zoning/zones.py — add build_pbf_filters sibling

**Files:**
- Modify: `src/zoning/zones.py`
- Test: `tests/zoning/test_zones.py` (new)

- [ ] **Step 8.1: Create tests directory and write failing test**

```bash
mkdir -p tests/zoning
touch tests/zoning/__init__.py
```

Create `tests/zoning/test_zones.py`:

```python
"""Tests for zoning.zones.build_pbf_filters."""
from __future__ import annotations

from zoning.zones import build_pbf_filters, build_queries
from shared.pbf_filters import FilterSpec, TagMatcher


BBOX = (44.86, -93.38, 45.05, -93.17)


def test_returns_filterspecs_with_same_keys_as_overpass():
    pbf = build_pbf_filters(BBOX)
    overpass = build_queries("44.86,-93.38,45.05,-93.17")
    assert set(pbf.keys()) == set(overpass.keys())


def test_apartments_filter_matches_apartments_building():
    pbf = build_pbf_filters(BBOX)
    spec = pbf["apartments"]
    assert isinstance(spec, FilterSpec)
    apt_clause = spec.clauses["apartments"]
    # At least one TagMatcher should match building=apartments
    assert any(m.matches({"building": "apartments"}) for m in apt_clause.tag_filters)


def test_civic_amenities_includes_schools_and_hospitals():
    pbf = build_pbf_filters(BBOX)
    spec = pbf["civic_amenities"]
    clause = next(iter(spec.clauses.values()))
    assert any(m.matches({"amenity": "school"}) for m in clause.tag_filters)
    assert any(m.matches({"amenity": "hospital"}) for m in clause.tag_filters)


def test_mixed_apartments_has_spatial_join():
    pbf = build_pbf_filters(BBOX)
    spec = pbf["mixed_apartments"]
    assert len(spec.spatial_joins) >= 1
    sj = spec.spatial_joins[0]
    assert sj.buffer_m == 5.0


def test_parking_matches_amenity_parking():
    pbf = build_pbf_filters(BBOX)
    spec = pbf["parking"]
    clause = next(iter(spec.clauses.values()))
    assert any(m.matches({"amenity": "parking"}) for m in clause.tag_filters)
```

- [ ] **Step 8.2: Run, verify fails**

```bash
cd src
uv run pytest ../tests/zoning/test_zones.py -v
```

Expected: FAIL with `ImportError: cannot import name 'build_pbf_filters'`.

- [ ] **Step 8.3: Implement build_pbf_filters**

Append to `src/zoning/zones.py`:

```python
# ── PBF filter specs (v3.4.0+) ───────────────────────────────────────────────
# Estos son siblings estructurados de las queries Overpass de arriba. Los
# extractores leen uno u otro según la flag --source.

from shared.pbf_filters import Clause, FilterSpec, SpatialJoin, TagMatcher


CIVIC_AMENITY_VALUES = [
    "school", "university", "college", "kindergarten",
    "hospital", "clinic", "doctors", "dentist", "pharmacy",
    "place_of_worship", "townhall", "courthouse", "public_building",
    "police", "fire_station", "post_office", "library",
    "community_centre", "social_facility", "theatre", "arts_centre",
    "cinema", "funeral_hall", "crematorium",
]

COMMERCIAL_AMENITY_VALUES = [
    "restaurant", "fast_food", "cafe", "bar", "pub",
    "fuel", "marketplace", "cinema", "theatre", "casino", "conference_centre",
]

MIXED_NODE_AMENITY_VALUES = ["restaurant", "cafe", "bar", "pub", "fast_food", "marketplace"]


def build_pbf_filters(bbox: tuple[float, float, float, float]) -> dict[str, FilterSpec]:
    """
    Sibling estructurado de build_queries(bbox_string).

    Devuelve un dict con las mismas keys (mixed_apartments, apartments,
    landuse_residential, residential_subtypes, commercial, office, industrial,
    parking, generic_buildings, civic_amenities) pero los valores son FilterSpec
    en lugar de Overpass QL strings.

    bbox: tuple (south, west, north, east). El argumento es el mismo bbox que
    se usaría para Overpass; aquí no se interpola en strings, se usa en el
    pbf_client al cargar el OSM().
    """
    return {
        "mixed_apartments": FilterSpec(
            clauses={
                "comm_nodes": Clause(
                    geom_types=["node"],
                    tag_filters=[
                        TagMatcher({"shop": True}),
                        TagMatcher({"amenity": MIXED_NODE_AMENITY_VALUES}),
                        TagMatcher({"tourism": "hotel"}),
                    ],
                ),
                "mixed_buildings": Clause(
                    geom_types=["way"],
                    tag_filters=[
                        TagMatcher({"building": "apartments"}),
                        TagMatcher({"building": "residential"}),
                        TagMatcher({"building": "mixed_use"}),
                        TagMatcher({"building:use": "mixed"}),
                        TagMatcher({"building:use": "residential;commercial"}),
                    ],
                ),
            },
            spatial_joins=[
                SpatialJoin(
                    anchor_clause="comm_nodes",
                    target_clause="mixed_buildings",
                    buffer_m=5.0,
                ),
            ],
        ),

        "apartments": FilterSpec(
            clauses={
                "apartments": Clause(
                    geom_types=["way"],
                    tag_filters=[
                        TagMatcher({"building": "apartments"}),
                        TagMatcher({"building": "residential"}),
                        TagMatcher({"building": "residential_tower"}),
                        TagMatcher({"building": "public_housing"}),
                        TagMatcher({"building": "council_house"}),
                        TagMatcher({"social_housing": "yes"}),
                    ],
                ),
            },
        ),

        "landuse_residential": FilterSpec(
            clauses={
                "lr": Clause(
                    geom_types=["way", "relation"],
                    tag_filters=[TagMatcher({"landuse": "residential"})],
                ),
            },
        ),

        "residential_subtypes": FilterSpec(
            clauses={
                "rs": Clause(
                    geom_types=["way"],
                    tag_filters=[
                        TagMatcher({"building": "terrace"}),
                        TagMatcher({"building": "townhouse"}),
                        TagMatcher({"building": "row_house"}),
                        TagMatcher({"building": "semi"}),
                        TagMatcher({"building": "semi_detached"}),
                        TagMatcher({"building": "semidetached_house"}),
                        TagMatcher({"building": "dormitory"}),
                        TagMatcher({"building": "house"}),
                        TagMatcher({"building": "detached"}),
                        TagMatcher({"building": "bungalow"}),
                    ],
                ),
            },
        ),

        "commercial": FilterSpec(
            clauses={
                "c": Clause(
                    geom_types=["way", "relation"],
                    tag_filters=(
                        [
                            TagMatcher({"landuse": "commercial"}),
                            TagMatcher({"landuse": "retail"}),
                            TagMatcher({"shop": True}),
                            TagMatcher({"building": "retail"}),
                            TagMatcher({"building": "supermarket"}),
                            TagMatcher({"building": "commercial"}),
                            TagMatcher({"tourism": "hotel"}),
                        ]
                        + [TagMatcher({"amenity": v}) for v in COMMERCIAL_AMENITY_VALUES]
                    ),
                ),
            },
        ),

        "office": FilterSpec(
            clauses={
                "o": Clause(
                    geom_types=["way", "relation"],
                    tag_filters=[
                        TagMatcher({"building": "office"}),
                        TagMatcher({"office": True}),
                        TagMatcher({"landuse": "office"}),
                    ],
                ),
            },
        ),

        "industrial": FilterSpec(
            clauses={
                "i": Clause(
                    geom_types=["way", "relation"],
                    tag_filters=[
                        TagMatcher({"landuse": "industrial"}),
                        TagMatcher({"building": "industrial"}),
                        TagMatcher({"building": "warehouse"}),
                        TagMatcher({"building": "factory"}),
                    ],
                ),
            },
        ),

        "parking": FilterSpec(
            clauses={
                "p": Clause(
                    geom_types=["way", "relation"],
                    tag_filters=[TagMatcher({"amenity": "parking"})],
                ),
            },
        ),

        "generic_buildings": FilterSpec(
            clauses={
                "gb": Clause(
                    geom_types=["way", "relation"],
                    tag_filters=[TagMatcher({"building": "yes"})],
                ),
            },
        ),

        "civic_amenities": FilterSpec(
            clauses={
                "ca": Clause(
                    geom_types=["node"],
                    tag_filters=[TagMatcher({"amenity": CIVIC_AMENITY_VALUES})],
                ),
            },
        ),
    }
```

- [ ] **Step 8.4: Run, verify pass**

```bash
cd src
uv run pytest ../tests/zoning/test_zones.py -v
```

Expected: 5 passed.

- [ ] **Step 8.5: Commit**

```bash
git add src/zoning/zones.py tests/zoning/__init__.py tests/zoning/test_zones.py
git commit -m "feat(zoning): add build_pbf_filters sibling to build_queries"
```

### Task 9: vial/zones.py and services/zones.py — add PBF filter siblings

**Files:**
- Modify: `src/vial/zones.py`
- Modify: `src/services/zones.py`
- Test: `tests/vial/test_zones.py` (new)
- Test: `tests/services/test_zones.py` (new)

- [ ] **Step 9.1: Write failing tests for vial**

```bash
mkdir -p tests/vial tests/services
touch tests/vial/__init__.py tests/services/__init__.py
```

Create `tests/vial/test_zones.py`:

```python
"""Tests for vial.zones.build_vial_pbf_filter."""
from vial.zones import build_vial_pbf_filter
from shared.pbf_filters import FilterSpec


def test_returns_filterspec():
    f = build_vial_pbf_filter((44.86, -93.38, 45.05, -93.17))
    assert isinstance(f, FilterSpec)


def test_matches_motorway_and_residential():
    f = build_vial_pbf_filter((44.86, -93.38, 45.05, -93.17))
    clause = next(iter(f.clauses.values()))
    assert any(m.matches({"highway": "motorway"}) for m in clause.tag_filters)
    assert any(m.matches({"highway": "residential"}) for m in clause.tag_filters)
    assert any(m.matches({"highway": "cycleway"}) for m in clause.tag_filters)


def test_does_not_match_random_tag():
    f = build_vial_pbf_filter((44.86, -93.38, 45.05, -93.17))
    clause = next(iter(f.clauses.values()))
    assert not any(m.matches({"building": "yes"}) for m in clause.tag_filters)
```

Create `tests/services/test_zones.py`:

```python
"""Tests for services.zones.build_services_pbf_filter."""
from services.zones import build_services_pbf_filter
from shared.pbf_filters import FilterSpec


def test_returns_filterspec():
    f = build_services_pbf_filter((44.86, -93.38, 45.05, -93.17))
    assert isinstance(f, FilterSpec)


def test_matches_hospital_and_school():
    f = build_services_pbf_filter((44.86, -93.38, 45.05, -93.17))
    matchers = [m for c in f.clauses.values() for m in c.tag_filters]
    assert any(m.matches({"amenity": "hospital"}) for m in matchers)
    assert any(m.matches({"amenity": "school"}) for m in matchers)


def test_matches_park_leisure():
    f = build_services_pbf_filter((44.86, -93.38, 45.05, -93.17))
    matchers = [m for c in f.clauses.values() for m in c.tag_filters]
    assert any(m.matches({"leisure": "park"}) for m in matchers)


def test_matches_cemetery_landuse():
    f = build_services_pbf_filter((44.86, -93.38, 45.05, -93.17))
    matchers = [m for c in f.clauses.values() for m in c.tag_filters]
    assert any(m.matches({"landuse": "cemetery"}) for m in matchers)
```

- [ ] **Step 9.2: Run, verify fails**

```bash
cd src
uv run pytest ../tests/vial/test_zones.py ../tests/services/test_zones.py -v
```

Expected: FAIL with `ImportError`.

- [ ] **Step 9.3: Implement vial/zones.py PBF filter**

Append to `src/vial/zones.py`:

```python
from shared.pbf_filters import Clause, FilterSpec, TagMatcher


VIAL_HIGHWAY_VALUES = [
    "motorway", "motorway_link", "trunk", "trunk_link",
    "primary", "primary_link", "secondary", "secondary_link",
    "tertiary", "tertiary_link", "residential", "unclassified",
    "living_street", "service",
    "pedestrian", "footway", "path", "steps",
    "cycleway",
]


def build_vial_pbf_filter(bbox: tuple[float, float, float, float]) -> FilterSpec:
    """
    Sibling estructurado de build_vial_query(bbox_string).

    Devuelve un FilterSpec que matchea ways con highway en VIAL_HIGHWAY_VALUES.
    """
    return FilterSpec(
        clauses={
            "highways": Clause(
                geom_types=["way"],
                tag_filters=[TagMatcher({"highway": VIAL_HIGHWAY_VALUES})],
            ),
        },
    )
```

- [ ] **Step 9.4: Implement services/zones.py PBF filter**

Append to `src/services/zones.py`:

```python
from shared.pbf_filters import Clause, FilterSpec, TagMatcher


SERVICES_AMENITY_VALUES = [
    "hospital", "clinic", "doctors", "funeral_directors", "crematorium",
    "school", "university", "college", "kindergarten", "research_institute",
    "fire_station",
    "police", "townhall", "courthouse", "prison", "library",
    "theatre", "arts_centre", "cinema",
]

SERVICES_LEISURE_VALUES = ["park", "nature_reserve", "garden", "playground", "sports_centre"]

SERVICES_OFFICE_VALUES = ["government", "research"]


def build_services_pbf_filter(bbox: tuple[float, float, float, float]) -> FilterSpec:
    """
    Sibling estructurado de build_services_query(bbox_string).

    Devuelve un FilterSpec con una clause única que matchea cualquiera de:
    amenity ∈ SERVICES_AMENITY_VALUES, leisure ∈ SERVICES_LEISURE_VALUES,
    landuse=cemetery, office ∈ SERVICES_OFFICE_VALUES, tourism=museum.
    """
    return FilterSpec(
        clauses={
            "services": Clause(
                geom_types=["node", "way"],
                tag_filters=[
                    TagMatcher({"amenity": SERVICES_AMENITY_VALUES}),
                    TagMatcher({"leisure": SERVICES_LEISURE_VALUES}),
                    TagMatcher({"landuse": "cemetery"}),
                    TagMatcher({"office": SERVICES_OFFICE_VALUES}),
                    TagMatcher({"tourism": "museum"}),
                ],
            ),
        },
    )
```

- [ ] **Step 9.5: Run, verify pass**

```bash
cd src
uv run pytest ../tests/vial/test_zones.py ../tests/services/test_zones.py -v
```

Expected: 7 passed.

- [ ] **Step 9.6: Commit**

```bash
git add src/vial/zones.py src/services/zones.py tests/vial/__init__.py tests/vial/test_zones.py tests/services/__init__.py tests/services/test_zones.py
git commit -m "feat(vial,services): add build_*_pbf_filter siblings"
```

### Task 10: cities.json + registry — add pbf_region field

**Files:**
- Modify: `cities.json` (add `pbf_region` to each city)
- Modify: `src/shared/registry.py` (validate optional field)
- Test: `tests/shared/test_registry_pbf_region.py` (new)

- [ ] **Step 10.1: Write failing test for pbf_region validation**

Create `tests/shared/test_registry_pbf_region.py`:

```python
"""Tests for shared.registry pbf_region handling."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from shared.registry import load_cities, get_city


def test_load_city_with_pbf_region(tmp_path: Path):
    cities_file = tmp_path / "cities.json"
    cities_file.write_text(json.dumps({
        "test": {
            "display_name": "Test",
            "country": "X",
            "bbox": [0, 0, 1, 1],
            "center": [0.5, 0.5],
            "zoom": 12,
            "tagline": "",
            "locale": "es",
            "pbf_region": "europe/test-country",
        }
    }))
    cities = load_cities(cities_file)
    entry = get_city(cities, "test")
    assert entry["pbf_region"] == "europe/test-country"


def test_load_city_without_pbf_region_ok(tmp_path: Path):
    """pbf_region es opcional — ciudades sin él siguen siendo válidas (usan Overpass)."""
    cities_file = tmp_path / "cities.json"
    cities_file.write_text(json.dumps({
        "test": {
            "display_name": "Test",
            "country": "X",
            "bbox": [0, 0, 1, 1],
            "center": [0.5, 0.5],
            "zoom": 12,
            "tagline": "",
            "locale": "es",
        }
    }))
    cities = load_cities(cities_file)
    entry = get_city(cities, "test")
    assert "pbf_region" not in entry or entry.get("pbf_region") is None
```

- [ ] **Step 10.2: Run baseline (verify registry.py works as-is)**

```bash
cd src
uv run pytest ../tests/shared/test_registry_pbf_region.py -v
```

Expected: Both PASS (registry.py likely doesn't reject unknown optional fields). If they fail, examine `src/shared/registry.py` for strict-schema validation and relax it for the new field.

- [ ] **Step 10.3: Update cities.json with pbf_region**

Edit `cities.json`. For each existing city, add `pbf_region`. Confirmed mappings:

| Slug | pbf_region |
|---|---|
| minneapolis | `north-america/us/minnesota` |
| amsterdam | `europe/netherlands` |
| madison | `north-america/us/wisconsin` |
| charleston | `north-america/us/south-carolina` |
| mafra_sc_brazil | `south-america/brazil/sul` |
| trondheim | `europe/norway` |
| bacau_ro | `europe/romania` |

For any city not in this table, use the appropriate Geofabrik path (look up at https://download.geofabrik.de/).

Add the field to each entry. Example for minneapolis:

```json
"minneapolis": {
    "display_name": "Minneapolis, MN",
    "country": "USA",
    "bbox": [44.86, -93.38, 45.05, -93.17],
    "center": [44.97, -93.27],
    "zoom": 12,
    "tagline": "Ciudad hero — fully featured",
    "locale": "es",
    "pbf_region": "north-america/us/minnesota"
}
```

- [ ] **Step 10.4: Verify JSON is still valid**

```bash
python -c "import json; json.load(open('cities.json'))"
```

Expected: no output (silent success).

- [ ] **Step 10.5: Run all tests to make sure nothing regressed**

```bash
cd src
uv run pytest -v
```

Expected: All tests pass, including new ones from previous tasks.

- [ ] **Step 10.6: Commit**

```bash
git add cities.json tests/shared/test_registry_pbf_region.py
git commit -m "feat(registry): add optional pbf_region field per city"
```

### Task 11: Add --source flag to zoning/extract.py

**Files:**
- Modify: `src/zoning/extract.py`
- Test: `tests/zoning/test_extract_source_flag.py` (new)

- [ ] **Step 11.1: Read current main() and argument parsing**

```bash
grep -n "argparse\|add_argument\|def main" src/zoning/extract.py
```

Note the line ranges of `main()` and the argument parser block.

- [ ] **Step 11.2: Write failing test for CLI flag parsing**

Create `tests/zoning/test_extract_source_flag.py`:

```python
"""Tests for the --source CLI flag in zoning.extract."""
from __future__ import annotations

import sys

import pytest

from zoning.extract import parse_args


def test_default_source_is_pbf():
    args = parse_args(["--city", "minneapolis"])
    assert args.source == "pbf"


def test_source_overpass_accepted():
    args = parse_args(["--city", "minneapolis", "--source", "overpass"])
    assert args.source == "overpass"


def test_source_pbf_accepted():
    args = parse_args(["--city", "minneapolis", "--source", "pbf"])
    assert args.source == "pbf"


def test_invalid_source_rejected():
    with pytest.raises(SystemExit):
        parse_args(["--city", "minneapolis", "--source", "garbage"])
```

- [ ] **Step 11.3: Run, verify fails**

```bash
cd src
uv run pytest ../tests/zoning/test_extract_source_flag.py -v
```

Expected: FAIL (either parse_args doesn't exist, or doesn't accept --source).

- [ ] **Step 11.4: Refactor extract.py to expose parse_args + add --source**

Modify `src/zoning/extract.py` `main()` area. The pattern is:

1. Extract the existing argparse setup into a standalone `parse_args(argv: list[str] | None = None)` function.
2. Add the `--source` argument with choices `["pbf", "overpass"]`, default `"pbf"`.
3. In `main()`, branch on `args.source`:
   - `"pbf"`: resolve PBF via `pbf_cache.ensure_pbf(city_entry["pbf_region"])`, then for each source key call `pbf_client.query(pbf_path, bbox_tuple, build_pbf_filters(bbox_tuple)[key], label=key)`.
   - `"overpass"`: keep existing `query_with_retry(build_queries(bbox)[key], label=key)` path.

Concrete patch sketch (apply by editing the actual `main()`):

```python
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="CS2 OSM zoning extractor")
    p.add_argument("--city", help="city slug from cities.json")
    p.add_argument("--bbox", help="raw bbox as 'south,west,north,east' (requires --slug)")
    p.add_argument("--slug", help="output slug (required if --bbox)")
    p.add_argument(
        "--source",
        choices=["pbf", "overpass"],
        default="pbf",
        help="extraction source: 'pbf' (default, local Geofabrik) or 'overpass' (legacy)",
    )
    p.add_argument(
        "--refresh-pbf",
        action="store_true",
        help="force re-download of regional PBF even if cached",
    )
    return p.parse_args(argv)


def main() -> None:
    args = parse_args()
    # ... existing city resolution ...

    if args.source == "pbf":
        from shared.pbf_cache import ensure_pbf
        from shared.pbf_client import query as pbf_query
        from zoning.zones import build_pbf_filters

        city_entry = get_city(load_cities(CITIES_FILE), city_slug)
        pbf_region = city_entry.get("pbf_region")
        if not pbf_region:
            raise SystemExit(
                f"[ERROR] City '{city_slug}' has no 'pbf_region' in cities.json. "
                "Either add it or run with --source overpass."
            )
        pbf_path = ensure_pbf(pbf_region, force_refresh=args.refresh_pbf)

        bbox_tuple = tuple(map(float, bbox_str.split(",")))
        filter_specs = build_pbf_filters(bbox_tuple)
        raw = {}
        for source_key, spec in filter_specs.items():
            raw[source_key] = pbf_query(pbf_path, bbox_tuple, spec, label=source_key)["elements"]
    else:
        # Existing Overpass path — keep as-is
        queries = build_queries(bbox_str)
        raw = {}
        for source_key, query in queries.items():
            raw[source_key] = query_with_retry(query, label=source_key)["elements"]

    # ... rest of pipeline (classification, output) unchanged ...
```

Apply this edit. Reading and adapting the actual `main()` code to incorporate this branching is the engineer's responsibility — the structure above is the contract.

- [ ] **Step 11.5: Run flag tests, verify pass**

```bash
cd src
uv run pytest ../tests/zoning/test_extract_source_flag.py -v
```

Expected: 4 passed.

- [ ] **Step 11.6: Smoke test — actually run extraction with PBF source**

```bash
cd src
uv run extract-zoning --city minneapolis --source pbf 2>&1 | tail -40
```

Expected:
- First run: downloads `north-america/us/minnesota-latest.osm.pbf` to `~/.cache/cs2-osm-toolkit/pbf/` (~30MB, takes ~30s on decent connection)
- Per-source `[pbf:<key>] OK <N> elementos en <T>s` lines
- Final output file written to `visualizer/cities/minneapolis/zones.js`

If element counts are within ±20% of Overpass run, parity is acceptable. Larger divergence: investigate filter spec.

- [ ] **Step 11.7: Smoke test — run with --source overpass to verify backward compat**

```bash
cd src
uv run extract-zoning --city minneapolis --source overpass 2>&1 | tail -10
```

Expected: existing Overpass behavior, same output.

- [ ] **Step 11.8: Commit**

```bash
git add src/zoning/extract.py tests/zoning/test_extract_source_flag.py
git commit -m "feat(zoning): add --source pbf|overpass flag to extract-zoning"
```

### Task 12: Same migration for vial/extract.py

**Files:**
- Modify: `src/vial/extract.py`
- Test: `tests/vial/test_extract_source_flag.py` (new)

- [ ] **Step 12.1: Write failing test** (mirror Task 11.2 with `vial.extract.parse_args`)

Create `tests/vial/test_extract_source_flag.py`:

```python
"""Tests for the --source CLI flag in vial.extract."""
import pytest
from vial.extract import parse_args


def test_default_source_is_pbf():
    args = parse_args(["--city", "minneapolis"])
    assert args.source == "pbf"


def test_overpass_accepted():
    args = parse_args(["--city", "minneapolis", "--source", "overpass"])
    assert args.source == "overpass"


def test_invalid_source_rejected():
    with pytest.raises(SystemExit):
        parse_args(["--city", "minneapolis", "--source", "garbage"])
```

- [ ] **Step 12.2: Run, verify fails**

```bash
cd src
uv run pytest ../tests/vial/test_extract_source_flag.py -v
```

Expected: FAIL.

- [ ] **Step 12.3: Apply same parse_args + main() refactor pattern from Task 11.4**

In `src/vial/extract.py`:
- Extract argparse into `parse_args(argv=None)`
- Add `--source` and `--refresh-pbf` flags
- Branch in `main()`: PBF uses `build_vial_pbf_filter(bbox_tuple)` and `pbf_client.query(...)`; Overpass uses existing `build_vial_query` + `query_with_retry`.

- [ ] **Step 12.4: Run flag tests**

```bash
cd src
uv run pytest ../tests/vial/test_extract_source_flag.py -v
```

Expected: 3 passed.

- [ ] **Step 12.5: Smoke test PBF path**

```bash
cd src
uv run extract-vial --city minneapolis --source pbf 2>&1 | tail -20
```

Expected: PBF cache hit (already downloaded in Task 11), highways extracted in <30s.

- [ ] **Step 12.6: Commit**

```bash
git add src/vial/extract.py tests/vial/test_extract_source_flag.py
git commit -m "feat(vial): add --source pbf|overpass flag to extract-vial"
```

### Task 13: Same migration for services/extract.py

**Files:**
- Modify: `src/services/extract.py`
- Test: `tests/services/test_extract_source_flag.py` (new)

- [ ] **Step 13.1: Write failing test**

Create `tests/services/test_extract_source_flag.py`:

```python
"""Tests for the --source CLI flag in services.extract."""
import pytest
from services.extract import parse_args


def test_default_source_is_pbf():
    args = parse_args(["--city", "minneapolis"])
    assert args.source == "pbf"


def test_overpass_accepted():
    args = parse_args(["--city", "minneapolis", "--source", "overpass"])
    assert args.source == "overpass"


def test_invalid_rejected():
    with pytest.raises(SystemExit):
        parse_args(["--city", "minneapolis", "--source", "garbage"])
```

- [ ] **Step 13.2: Run, verify fails**

```bash
cd src
uv run pytest ../tests/services/test_extract_source_flag.py -v
```

Expected: FAIL.

- [ ] **Step 13.3: Apply same pattern in src/services/extract.py**

PBF branch uses `build_services_pbf_filter(bbox_tuple)` + `pbf_client.query(...)`.

- [ ] **Step 13.4: Run tests**

```bash
cd src
uv run pytest ../tests/services/test_extract_source_flag.py -v
```

Expected: 3 passed.

- [ ] **Step 13.5: Smoke test PBF path**

```bash
cd src
uv run extract-services --city minneapolis --source pbf 2>&1 | tail -20
```

Expected: services extracted in <30s.

- [ ] **Step 13.6: Commit**

```bash
git add src/services/extract.py tests/services/test_extract_source_flag.py
git commit -m "feat(services): add --source pbf|overpass flag to extract-services"
```

### Task 14: Same migration for extract_google_buildings.py

**Files:**
- Modify: `src/zoning/extract_google_buildings.py`

This file uses Overpass twice: landuse polygons (via `build_queries`) and civic amenities. Both have PBF equivalents from Task 8.

- [ ] **Step 14.1: Identify Overpass call sites**

```bash
grep -n "query_with_retry\|build_queries" src/zoning/extract_google_buildings.py
```

- [ ] **Step 14.2: Add --source flag and route both Overpass calls through the PBF branch**

Apply the same `parse_args` + branch pattern. The two source keys to fetch via PBF are at least `landuse_residential`, `commercial`, `industrial`, `office`, `civic_amenities` (check actual usage in the file).

Use a single `pbf_path = ensure_pbf(city_entry["pbf_region"], force_refresh=args.refresh_pbf)` at the top of `main()` (one cache lookup, multiple queries).

- [ ] **Step 14.3: Smoke test**

```bash
cd src
uv run extract-google-buildings --city minneapolis --source pbf 2>&1 | tail -30
```

Expected: pipeline runs end-to-end, output file in `visualizer/cities/minneapolis/google_buildings.js` (or equivalent).

- [ ] **Step 14.4: Commit**

```bash
git add src/zoning/extract_google_buildings.py
git commit -m "feat(zoning): add --source pbf flag to extract-google-buildings"
```

---

## Phase 5: Parity validation

### Task 15: End-to-end parity test

**Files:**
- Create: `tests/integration/test_pbf_overpass_parity.py`
- Create: `tests/integration/__init__.py`

- [ ] **Step 15.1: Create integration test**

```bash
touch tests/integration/__init__.py
```

Create `tests/integration/test_pbf_overpass_parity.py`:

```python
"""
End-to-end parity test: PBF source should produce element counts within
±20% of Overpass source for the same city.

Marked as integration — requires network (Overpass) and the regional PBF
cached. Skipped by default; run with: pytest -m integration -v
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.environ.get("CS2_PARITY_TEST") != "1",
    reason="Set CS2_PARITY_TEST=1 to run (network + ~5min runtime)",
)
def test_zoning_pbf_overpass_parity_minneapolis():
    """Element counts per source key within ±20% between PBF and Overpass."""
    from shared.registry import load_cities, get_city
    from shared.overpass_client import query_with_retry
    from shared.pbf_cache import ensure_pbf
    from shared.pbf_client import query as pbf_query
    from zoning.zones import build_queries, build_pbf_filters

    cities_file = Path(__file__).resolve().parents[2] / "cities.json"
    city = get_city(load_cities(cities_file), "minneapolis")
    bbox_tuple = tuple(city["bbox"])
    bbox_str = ",".join(str(v) for v in bbox_tuple)
    pbf_path = ensure_pbf(city["pbf_region"])

    overpass_queries = build_queries(bbox_str)
    pbf_specs = build_pbf_filters(bbox_tuple)

    for key in overpass_queries:
        op_count = len(query_with_retry(overpass_queries[key], label=f"op:{key}")["elements"])
        pbf_count = len(pbf_query(pbf_path, bbox_tuple, pbf_specs[key], label=f"pbf:{key}")["elements"])

        # Avoid div-by-zero
        if op_count == 0:
            assert pbf_count == 0, f"{key}: Overpass=0 but PBF={pbf_count}"
            continue

        ratio = pbf_count / op_count
        assert 0.8 <= ratio <= 1.2, (
            f"{key}: PBF={pbf_count}, Overpass={op_count}, ratio={ratio:.2f} "
            f"(expected 0.8-1.2)"
        )
```

- [ ] **Step 15.2: Register integration marker in pyproject**

Modify `src/pyproject.toml` (add to bottom):

```toml
[tool.pytest.ini_options]
markers = [
    "integration: requires network and large fixtures (opt-in via CS2_PARITY_TEST=1)",
]
```

- [ ] **Step 15.3: Run parity test manually (one-off, not in CI)**

```bash
cd src
CS2_PARITY_TEST=1 uv run pytest ../tests/integration/test_pbf_overpass_parity.py -v -s
```

Expected:
- Takes ~5 minutes (multiple Overpass queries)
- All source keys within ±20%
- If a key fails parity, investigate the corresponding `TagMatcher` list in `zoning/zones.py` — likely missing a value.

- [ ] **Step 15.4: If parity fails for any key, fix and re-test**

Common fixes:
- Missing tag value in `TagMatcher` (e.g., Overpass query had `building:use~"residential"` and we only matched `building:use=residential` exact — needs adjustment or accept the gap)
- Geometry mismatch (Polygon vs MultiPolygon) — make sure `_geometry_to_overpass_relation` handles all cases
- pyrosm not loading nodes-with-tags — verify `_extract_all_geom_types` calls `get_pois()` for node geom types

Repeat Step 15.3 until pass.

- [ ] **Step 15.5: Commit**

```bash
git add tests/integration/__init__.py tests/integration/test_pbf_overpass_parity.py src/pyproject.toml
git commit -m "test: add PBF/Overpass parity integration test (opt-in)"
```

---

## Phase 6: Docs & release

### Task 16: Update README + CHANGELOG

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 16.1: Add "Data source" section to README**

In `README.md`, after the "Quick start" section, add:

```markdown
## Data source: PBF (default) vs Overpass (legacy)

Starting with **v3.4.0**, the toolkit extracts from local `.osm.pbf` files
downloaded from [Geofabrik](https://download.geofabrik.de/) by default.

**Why:** PBF extraction is 10-50× faster than Overpass per city, has no rate
limits, is fully reproducible (same PBF + same bbox = same output), and
doesn't consume shared community resources.

**How:**

1. Each city in `cities.json` declares its `pbf_region`:

   ```json
   "minneapolis": {
       ...,
       "pbf_region": "north-america/us/minnesota"
   }
   ```

2. The first extraction of a city downloads the regional PBF to
   `~/.cache/cs2-osm-toolkit/pbf/` (cached for 7 days, then refreshed).

3. Subsequent extractions of any city in the same region use the cache.

**Storage:** A US state PBF is ~30 MB; a country is 100 MB - 2 GB. Plan accordingly.

**Refresh cache:**

```bash
uv run extract-zoning --city minneapolis --refresh-pbf
```

**Legacy Overpass mode** (no longer recommended, will be removed in v4.0.0):

```bash
uv run extract-zoning --city minneapolis --source overpass
```
```

- [ ] **Step 16.2: Add v3.4.0 CHANGELOG entry**

Append to top of `CHANGELOG.md`:

```markdown
## v3.4.0 — 2026-XX-XX

### Added
- **PBF-based extraction (default):** Replaces Overpass for all extractors.
  10-50× faster, no rate limits, fully reproducible. Uses Geofabrik regional
  dumps via `pyrosm`.
- New `pbf_region` field in `cities.json` per city (e.g.
  `"north-america/us/minnesota"`).
- New `shared/pbf_cache.py`: downloads + caches regional PBFs with 7-day TTL.
- New `shared/pbf_client.py`: PBF reader with Overpass-compatible JSON output.
- New `shared/pbf_filters.py`: structured filter spec types (`FilterSpec`,
  `Clause`, `TagMatcher`, `SpatialJoin`).
- `build_pbf_filters()` siblings in `zoning/`, `vial/`, `services/` zones modules.
- `--source pbf|overpass` and `--refresh-pbf` CLI flags on all `extract-*` commands.

### Changed
- Default extraction source is now `pbf` for all commands.
- Bumped `pyrosm>=0.6.2` to dependencies.

### Deprecated
- `--source overpass` mode is kept as fallback but will be removed in v4.0.0.
- `shared/overpass_client.py` will be removed in v4.0.0.

### Migration notes
Existing users: re-run any `extract-*` command — it will auto-download the
regional PBF for your city's `pbf_region` on first use. To opt back into the
old behavior temporarily: append `--source overpass`.
```

- [ ] **Step 16.3: Verify all tests still pass**

```bash
cd src
uv run pytest -v
```

Expected: All non-integration tests pass.

- [ ] **Step 16.4: Commit**

```bash
git add README.md CHANGELOG.md
git commit -m "docs: document PBF extraction workflow for v3.4.0"
```

### Task 17: Tag and release v3.4.0

- [ ] **Step 17.1: Verify version in pyproject.toml is 3.4.0**

```bash
grep "^version" src/pyproject.toml
```

Expected: `version = "3.4.0"`.

- [ ] **Step 17.2: Sync uv.lock**

```bash
cd src
uv sync
```

- [ ] **Step 17.3: Final full test run**

```bash
cd src
uv run pytest -v
```

Expected: All tests pass.

- [ ] **Step 17.4: Manual end-to-end on Minneapolis**

```bash
cd src
uv run extract-zoning --city minneapolis --source pbf
uv run extract-vial --city minneapolis --source pbf
uv run extract-services --city minneapolis --source pbf
```

Expected: All three complete successfully. Open `visualizer/cities/minneapolis/index.html` and visually confirm the map looks correct.

- [ ] **Step 17.5: Commit lockfile if changed**

```bash
git add src/uv.lock
git diff --cached --quiet && echo "no lockfile changes" || git commit -m "chore: sync uv.lock for v3.4.0"
```

- [ ] **Step 17.6: Tag v3.4.0**

```bash
git tag -a v3.4.0 -m "v3.4.0 — PBF extraction default"
git push origin main
git push origin v3.4.0
```

Expected: tag pushed; GitHub Pages deployment triggers automatically (per existing workflow).

- [ ] **Step 17.7: Verify deployment**

After ~2 min, check the live site loads and the `manifest.json` reports v3.4.0.

---

## Self-Review

**Spec coverage check:**
- ✓ Replace Overpass with PBF: Tasks 0-7 (infrastructure), 11-14 (per-module migration)
- ✓ Preserve Overpass-shape contract for consumers: `pbf_client._build_overpass_element` (Task 7)
- ✓ Per-region PBF caching with TTL: Task 1
- ✓ Backward compat (Overpass as fallback): `--source` flag in Tasks 11-14
- ✓ Parity validation: Task 15
- ✓ Documentation: Task 16
- ✓ Release: Task 17

**Placeholder scan:** Reviewed steps for "TBD" / "implement later" / "add validation" — none found. Task 11.4 contains a pattern description rather than verbatim code because the existing `main()` function is complex and unread by me at plan time; engineer must read it and apply the pattern. This is intentional, not a placeholder.

**Type consistency:**
- `FilterSpec`, `Clause`, `TagMatcher`, `SpatialJoin` — used consistently across Tasks 2, 8, 9, 11-14.
- `query_with_retry(pbf_path, bbox, filter_spec, label)` in `pbf_client` vs `query_with_retry(query, label)` in `overpass_client` — DIFFERENT signatures. Note: callers do not import both at once; each extractor calls the right one based on `--source`. Documented in Task 7.

**One known limitation:** `_extract_all_geom_types` calls `get_buildings + get_landuse + get_pois + get_network` and dedupes. This may miss some edge tags that pyrosm doesn't surface in those getters (e.g., `social_housing=yes` without a building tag). Task 15 parity test will catch this; if it does, fall back to `osm.get_data_by_custom_criteria()` for the affected source key.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-18-pbf-migration.md`. Two execution options:

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks, fast iteration. Best for this plan because tasks are independent (each ends with a commit), reviewable in isolation, and we can catch issues early before they cascade.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints. Slower context-wise but you see everything in one place.

**Which approach?**
