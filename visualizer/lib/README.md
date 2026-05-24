# Vendored Libraries

Third-party JS libraries vendored to this directory for runtime use by `visualizer/generate.html`. Pinned versions for reproducibility.

| Library | Version | Source | Last updated |
|---|---|---|---|
| JSZip | 3.10.1 | https://github.com/Stuk/jszip | 2026-05-21 |
| UPNG.js | 2.1.0 | https://github.com/photopea/UPNG.js | 2026-05-21 |
| pako | 2.1.0 | https://github.com/nodeca/pako | 2026-05-21 |

JSZip is dual-licensed under the MIT license or GPLv3. UPNG.js and pako are MIT-licensed. See their respective repos for source code and license details.

## Dependency note

UPNG.js requires `pako` at runtime for PNG inflate/deflate. Both must be loaded before any UPNG operation. Script load order in `generate.html`: pako → upng → (jszip independent).

## Why vendored

These are loaded by `<script>` tag from `generate.html`, so they need to live in the static asset tree. Vendoring (vs CDN at runtime):
- No runtime CDN dependency
- Auditable updates via git commits
- Hosted under same origin (no CORS surprises)

## Updating

Re-run the curl commands in `docs/superpowers/plans/2026-05-18-osm2cs-generator.md` Task 1 to fetch latest versions. Test thoroughly before bumping pinned versions in this README.
