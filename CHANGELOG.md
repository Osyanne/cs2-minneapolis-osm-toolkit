# Changelog

All notable changes to the cs2-osm-toolkit. The format is loosely based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
follows [Semantic Versioning](https://semver.org/).

## [v3.4.0] — 2026-05-19

### Added

- **PBF-based extraction (default):** All four `extract-*` commands now read
  from local `.osm.pbf` files downloaded from Geofabrik by default, instead
  of the Overpass API. Faster per city, no rate limits, fully reproducible,
  and aligned with OSM community guidance against bulk-extracting from
  Overpass.
- New `pbf_region` field in `cities.json` per city (e.g.
  `"north-america/us/minnesota"`).
- New `src/shared/pbf_cache.py`: downloads + caches regional PBFs in
  `~/.cache/cs2-osm-toolkit/pbf/` with a 7-day TTL. `--refresh-pbf` flag
  forces a re-download.
- New `src/shared/pbf_filters.py`: structured filter spec types
  (`FilterSpec`, `Clause`, `TagMatcher`, `SpatialJoin`) that replace
  Overpass QL strings as the filter contract.
- New `src/shared/pbf_client.py`: PBF reader using `pyosmium 4.x`
  `FileProcessor` API. Emits Overpass-compatible JSON so existing
  classification + output code is unchanged.
- `build_pbf_filters()` siblings in `zoning/zones.py`, `vial/zones.py`,
  `services/zones.py` — return structured filter specs equivalent to the
  existing `build_queries()` / `build_*_query()` Overpass QL builders.
- `--source pbf|overpass` and `--refresh-pbf` CLI flags on
  `extract-zoning`, `extract-vial`, `extract-services`, and
  `extract-google-buildings`.
- Opt-in parity integration test (`tests/integration/test_pbf_overpass_parity.py`)
  comparing PBF and Overpass element counts per source key (±20%
  tolerance). Run with `CS2_PARITY_TEST=1`.

### Changed

- Default extraction source is now `pbf` for every `extract-*` command.
- Added `osmium>=3.7.0` (pyosmium) to dependencies. Resolves to 4.3.1 in
  practice; use the 4.x API surface.
- Bumped `version` to `3.4.0` in `src/pyproject.toml`.
- Test suite grew from 184 to 281 passing tests (+97), all green.

### Deprecated

- `--source overpass` mode is kept as a fallback but will be removed in
  v4.0.0.
- `src/shared/overpass_client.py` will be removed in v4.0.0.

### Known Limitations

- **Per-source full-file re-read:** `extract-zoning` reads the regional PBF
  10 times (one per source category), making each city ~3–7 min on a 30 MB
  state PBF. A batched single-pass API is planned for v3.5.0.
- **Longitude buffer approximation in spatial join:** 1° latitude ≈ 111 km
  is used for both axes, overstating longitude at non-equatorial latitudes
  (~40% at 45°N). Acceptable for 5–10 m "around" semantics used in the
  mixed-apartments matcher; revisit if larger buffers are introduced.
- **Compound-tag regex approximation:** Overpass patterns like
  `["building:use"~"residential"]` are approximated as list-equality in
  PBF filters (`["residential", "residential;commercial"]`). Some rare
  multi-value `building:use` tags may go unmatched.

### Migration Notes

Existing users: re-run any `extract-*` command — it will auto-download the
regional PBF for your city's `pbf_region` on first use, then reuse the
cache. To opt back into Overpass temporarily: append `--source overpass`.

If your city in `cities.json` does not have `pbf_region`, the extractor
will exit with a clear error telling you to add it or fall back to
`--source overpass`. The seven default cities (Minneapolis, Amsterdam,
Madison, Charleston, Mafra, Trondheim, Bacau) all have `pbf_region`
preconfigured.

---

## [v3.3.x] and earlier

See git history (`git log --oneline`) for changes prior to v3.4.0. The
toolkit was renamed from `cs2-minneapolis-osm-toolkit` to
`CitiesSkylines2-osm-toolkit` in May 2026, and the multi-city architecture
landed across the v3.x series.
