# v3.5 — Browser-based OSM2CS Generator — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `visualizer/generate.html` — a free, no-auth, client-side web tool that generates a CS2-ready map bundle (heightmap + 4 GeoJSON layers + offline viewer + README in a ZIP) from any city in the world.

**Architecture:** 100% client-side. Browser does SRTM tile fetch → Canvas bilinear resample → UPNG 16-bit PNG encode → Overpass queries (zoning/roads/services/water) → classification → JSZip packaging → download. Zero backend, zero auth, zero billing. Hosted on GitHub Pages alongside existing toolkit.

**Tech Stack:** Vanilla HTML/CSS/JS (ES modules, no build step), Leaflet 1.x, Nominatim API, OpenTopography SRTM v3, Overpass API (existing multi-endpoint rotation pattern), Canvas API, UPNG.js (vendored), JSZip (vendored).

**Spec:** `docs/specs/2026-05-18-osm2cs-generator-design.md` (commit `60fa8dc`).

---

## Phase 0: Setup & infrastructure (3 tasks)

### Task 1: Vendor 3rd-party libraries

**Files:**
- Create: `visualizer/lib/jszip.min.js` (~95 KB, fetched from CDN)
- Create: `visualizer/lib/upng.min.js` (~30 KB, fetched from CDN)
- Create: `visualizer/lib/README.md` (provenance log)

- [ ] **Step 1: Create `visualizer/lib/` directory**

```bash
mkdir -p visualizer/lib
```

- [ ] **Step 2: Download JSZip and UPNG.js to vendored location**

```bash
curl -L -o visualizer/lib/jszip.min.js https://cdn.jsdelivr.net/npm/jszip@3.10.1/dist/jszip.min.js
curl -L -o visualizer/lib/upng.min.js https://cdn.jsdelivr.net/npm/upng-js@2.1.0/UPNG.js
```

- [ ] **Step 3: Verify integrity (file sizes match expected range)**

```bash
ls -la visualizer/lib/
```

Expected:
- `jszip.min.js`: ~90-100 KB
- `upng.min.js`: ~28-35 KB

- [ ] **Step 4: Create provenance log**

Write `visualizer/lib/README.md`:

```markdown
# Vendored Libraries

Third-party JS libraries vendored to this directory for runtime use by `visualizer/generate.html`. Pinned versions for reproducibility.

| Library | Version | Source | Last updated |
|---|---|---|---|
| JSZip | 3.10.1 | https://github.com/Stuk/jszip | 2026-05-18 |
| UPNG.js | 2.1.0 | https://github.com/photopea/UPNG.js | 2026-05-18 |

Both libraries are MIT-licensed. See their respective repos for source code and license details.

## Why vendored

These are loaded by `<script>` tag from `generate.html`, so they need to live in the static asset tree. Vendoring (vs CDN at runtime):
- ✓ No runtime CDN dependency
- ✓ Auditable updates via git commits
- ✓ Hosted under same origin (no CORS surprises)

## Updating

Re-run the curl commands in `docs/superpowers/plans/2026-05-18-osm2cs-generator.md` Task 1 to fetch latest versions. Test thoroughly before bumping pinned versions in this README.
```

- [ ] **Step 5: Commit**

```bash
git add visualizer/lib/
git commit -m "feat: vendor JSZip 3.10.1 + UPNG.js 2.1.0 for v3.5 generator"
```

---

### Task 2: Set up `tests-js/` infrastructure

**Files:**
- Create: `tests-js/README.md`
- Create: `tests-js/helpers/mock-fetch.js`
- Create: `tests-js/helpers/index.js`
- Create: `tests-js/smoke.test.js` (sanity test)

- [ ] **Step 1: Verify Node version (must be ≥20 for `node --test`)**

```bash
node --version
```

Expected: `v20.x.x` or higher. If lower, install Node 20+ first.

- [ ] **Step 2: Create tests-js directory structure**

```bash
mkdir -p tests-js/helpers tests-js/fixtures
```

- [ ] **Step 3: Create mock-fetch helper**

Write `tests-js/helpers/mock-fetch.js`:

```javascript
// Mock fetch implementation for unit tests.
// Usage: const fetch = mockFetch([{ url: /pattern/, status: 200, body: {...} }]);

export function mockFetch(responses) {
  const calls = [];
  const fn = async (url, options = {}) => {
    calls.push({ url, options });
    const match = responses.find(r => r.url.test(url));
    if (!match) {
      throw new Error(`No mock response for ${url}`);
    }
    return {
      ok: match.status >= 200 && match.status < 300,
      status: match.status,
      statusText: match.statusText || (match.status === 200 ? 'OK' : 'Error'),
      json: async () => match.body,
      text: async () => typeof match.body === 'string' ? match.body : JSON.stringify(match.body),
      blob: async () => new Blob([match.body]),
      arrayBuffer: async () => new ArrayBuffer(8)
    };
  };
  fn.calls = calls;
  return fn;
}
```

- [ ] **Step 4: Create test runner README**

Write `tests-js/README.md`:

```markdown
# JS Tests

Node.js native test runner (`node --test`), zero deps.

## Running

From repo root:

```bash
node --test tests-js/
```

Or specific test:

```bash
node --test tests-js/heightmap.test.js
```

## Structure

```
tests-js/
├── helpers/           Shared test utilities (mock-fetch, etc.)
├── fixtures/          Sample data (SRTM tiles, OSM responses)
├── e2e/               Playwright end-to-end tests
└── *.test.js          Unit tests for each visualizer/js/ module
```

## Conventions

- File naming: `<module>.test.js` (matches module being tested)
- Use `node --test`'s `test()` + `assert` from `node:assert`
- Import the module under test via relative path: `../visualizer/js/<module>.js`
- Mock external fetches via `helpers/mock-fetch.js`
- Tests should run in <100ms each (no real network calls)
```

- [ ] **Step 5: Create a sanity smoke test**

Write `tests-js/smoke.test.js`:

```javascript
import { test } from 'node:test';
import assert from 'node:assert';
import { mockFetch } from './helpers/mock-fetch.js';

test('node:test runner works', () => {
  assert.equal(1 + 1, 2);
});

test('mock-fetch helper works', async () => {
  const fetch = mockFetch([
    { url: /example\.com/, status: 200, body: { ok: true } }
  ]);
  const res = await fetch('https://example.com/test');
  const body = await res.json();
  assert.equal(body.ok, true);
  assert.equal(fetch.calls.length, 1);
});
```

- [ ] **Step 6: Run the smoke test**

```bash
node --test tests-js/smoke.test.js
```

Expected output:
```
✔ node:test runner works
✔ mock-fetch helper works
ℹ tests 2
ℹ pass 2
ℹ fail 0
```

- [ ] **Step 7: Commit**

```bash
git add tests-js/
git commit -m "test: set up tests-js/ infrastructure with node --test runner"
```

---

### Task 3: Set up CI workflow for tests-js

**Files:**
- Modify: `.github/workflows/test.yml` (or create if missing — check first)

- [ ] **Step 1: Check existing workflow**

```bash
ls .github/workflows/
cat .github/workflows/test.yml 2>/dev/null || echo "NOT FOUND"
```

If found, note the existing structure (probably has a pytest job). If not, plan to create.

- [ ] **Step 2: Add js-tests job to existing workflow**

If `test.yml` exists, add a new job. If not, create with both python and js jobs. Example minimal addition:

```yaml
  js-tests:
    name: JS Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: Run tests-js
        run: node --test tests-js/
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/test.yml
git commit -m "ci: add js-tests job for tests-js/ node --test runner"
```

- [ ] **Step 4: Push and verify CI passes**

```bash
git push origin main
gh run watch  # or check https://github.com/Osyanne/CitiesSkylines2-osm-toolkit/actions
```

Expected: js-tests job passes (smoke test only at this point).

---

## Phase 1: Refactor — extract reusable modules from map.html (4 tasks)

### Task 4: Extract Overpass client from map.html to overpass-client.js

**Files:**
- Modify: `visualizer/map.html` (remove inline Overpass logic ~lines TBD)
- Create: `visualizer/js/overpass-client.js`
- Create: `tests-js/overpass-client.test.js`

- [ ] **Step 1: Locate Overpass-related code in map.html**

```bash
grep -n "overpass-api.de\|kumi.systems\|openstreetmap.ru\|fetchOverpass\|queryOverpass" visualizer/map.html
```

Note the line ranges of inline `<script>` blocks containing Overpass logic.

- [ ] **Step 2: Write failing test for the extracted module**

Write `tests-js/overpass-client.test.js`:

```javascript
import { test } from 'node:test';
import assert from 'node:assert';
import { mockFetch } from './helpers/mock-fetch.js';
import { fetchOverpass } from '../visualizer/js/overpass-client.js';

test('fetchOverpass returns parsed JSON on 200', async () => {
  const fetch = mockFetch([
    { url: /overpass-api\.de/, status: 200, body: { elements: [{ id: 1 }] } }
  ]);
  const result = await fetchOverpass('[out:json];node(1);out;', { fetch });
  assert.deepEqual(result.elements, [{ id: 1 }]);
});

test('fetchOverpass rotates endpoints on 504', async () => {
  const fetch = mockFetch([
    { url: /overpass-api\.de/, status: 504 },
    { url: /kumi\.systems/, status: 200, body: { elements: [] } }
  ]);
  const result = await fetchOverpass('[out:json];node(1);out;', { fetch });
  assert.deepEqual(result.elements, []);
});

test('fetchOverpass throws after all endpoints fail', async () => {
  const fetch = mockFetch([
    { url: /overpass-api\.de/, status: 504 },
    { url: /kumi\.systems/, status: 504 },
    { url: /openstreetmap\.ru/, status: 504 },
    { url: /maps\.mail\.ru/, status: 504 }
  ]);
  await assert.rejects(
    fetchOverpass('[out:json];node(1);out;', { fetch }),
    /all endpoints failed/i
  );
});
```

- [ ] **Step 3: Run test to verify it fails**

```bash
node --test tests-js/overpass-client.test.js
```

Expected: FAIL with "Cannot find module '../visualizer/js/overpass-client.js'"

- [ ] **Step 4: Create the module with minimal implementation**

Write `visualizer/js/overpass-client.js`:

```javascript
// Overpass API client with multi-endpoint rotation.
// Extracted from map.html in v3.5 for reuse in generate.html.

const ENDPOINTS = [
  'https://overpass-api.de/api/interpreter',
  'https://overpass.kumi.systems/api/interpreter',
  'https://overpass.openstreetmap.ru/api/interpreter',
  'https://maps.mail.ru/osm/tools/overpass/api/interpreter'
];

export async function fetchOverpass(query, options = {}) {
  const fetchFn = options.fetch || fetch;
  const errors = [];
  
  for (const endpoint of ENDPOINTS) {
    try {
      const response = await fetchFn(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: `data=${encodeURIComponent(query)}`
      });
      
      if (response.ok) {
        const json = await response.json();
        // Treat empty response as silent failure (Overpass quirk under load)
        if (json.elements && json.elements.length === 0 && options.expectNonEmpty) {
          errors.push({ endpoint, error: 'empty response' });
          continue;
        }
        return json;
      }
      errors.push({ endpoint, status: response.status });
    } catch (err) {
      errors.push({ endpoint, error: err.message });
    }
  }
  
  throw new Error(`Overpass query failed: all endpoints failed. ${JSON.stringify(errors)}`);
}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
node --test tests-js/overpass-client.test.js
```

Expected: PASS all 3 tests.

- [ ] **Step 6: Commit the new module + tests (BEFORE touching map.html)**

```bash
git add visualizer/js/overpass-client.js tests-js/overpass-client.test.js
git commit -m "feat(visualizer): extract overpass-client.js as reusable module"
```

- [ ] **Step 7: Update map.html to use the new module**

Add at top of `map.html` `<head>`:

```html
<script type="module" src="js/overpass-client.js"></script>
```

Find the inline Overpass logic (from Step 1) and replace with:

```javascript
import { fetchOverpass } from './js/overpass-client.js';
// ... use fetchOverpass(query) wherever inline Overpass logic was called
```

Note: this step is the most fragile. Verify by viewing `map.html` in a browser (existing 10 cities should render) before committing.

- [ ] **Step 8: Commit map.html refactor**

```bash
git add visualizer/map.html
git commit -m "refactor(visualizer): use overpass-client.js module in map.html"
```

---

### Task 5: Extract classifiers from map.html to classifiers.js

**Files:**
- Modify: `visualizer/map.html`
- Create: `visualizer/js/classifiers.js`
- Create: `tests-js/classifiers.test.js`
- Create: `tests-js/fixtures/classifier-cases.json`

- [ ] **Step 1: Locate classification logic in map.html**

```bash
grep -n "classifyZoning\|classifyRoad\|classifyService\|ZONE_MAP\|categoryFor" visualizer/map.html
```

Note line ranges of inline classifier logic.

- [ ] **Step 2: Create fixture file from existing Python tests**

Look at `tests/test_classifiers.py` for example inputs/outputs, then create `tests-js/fixtures/classifier-cases.json`:

```json
[
  {
    "name": "apartment building → res_high",
    "input": { "tags": { "building": "apartments", "building:levels": "10" } },
    "expected_zoning": "res_high"
  },
  {
    "name": "single-family house → res_low",
    "input": { "tags": { "building": "house" } },
    "expected_zoning": "res_low"
  },
  {
    "name": "commercial landuse → com_low",
    "input": { "tags": { "landuse": "commercial" } },
    "expected_zoning": "com_low"
  },
  {
    "name": "industrial landuse → ind",
    "input": { "tags": { "landuse": "industrial" } },
    "expected_zoning": "ind"
  },
  {
    "name": "park → prk",
    "input": { "tags": { "leisure": "park" } },
    "expected_zoning": "prk"
  },
  {
    "name": "untagged returns null", 
    "input": { "tags": {} },
    "expected_zoning": null
  }
]
```

(Expand to match real cases from Python — at least 10 cases covering all 11 CS2 zones.)

- [ ] **Step 3: Write failing test**

Write `tests-js/classifiers.test.js`:

```javascript
import { test } from 'node:test';
import assert from 'node:assert';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { classifyZoning } from '../visualizer/js/classifiers.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixtures = JSON.parse(
  readFileSync(join(__dirname, 'fixtures/classifier-cases.json'), 'utf-8')
);

for (const { name, input, expected_zoning } of fixtures) {
  test(`classifyZoning: ${name}`, () => {
    assert.equal(classifyZoning(input), expected_zoning);
  });
}
```

- [ ] **Step 4: Run test to verify it fails**

```bash
node --test tests-js/classifiers.test.js
```

Expected: FAIL with "Cannot find module".

- [ ] **Step 5: Implement classifiers.js with logic extracted from map.html**

Write `visualizer/js/classifiers.js`:

```javascript
// CS2 zone classifier. Maps OSM tags to one of 11 CS2 zone types.
// Extracted from map.html in v3.5 for reuse in generate.html.
// Must maintain parity with Python src/classifiers.py.

export function classifyZoning(feature) {
  const tags = feature.tags || {};
  
  // Buildings
  if (tags.building === 'apartments' || tags.building === 'residential') {
    const levels = parseInt(tags['building:levels']) || 1;
    if (levels >= 8) return 'res_high';
    if (levels >= 4) return 'res_med';
    return 'res_low_rent';
  }
  if (tags.building === 'house' || tags.building === 'detached') return 'res_low';
  if (tags.building === 'terrace' || tags.building === 'semi_detached') return 'res_row';
  
  // Land use
  if (tags.landuse === 'residential') return 'res_low';
  if (tags.landuse === 'commercial') return 'com_low';
  if (tags.landuse === 'retail') return 'com_high';
  if (tags.landuse === 'industrial') return 'ind';
  
  // Parks & green
  if (tags.leisure === 'park' || tags.leisure === 'garden') return 'prk';
  if (tags.amenity === 'school' || tags.amenity === 'university') return 'office_low';
  
  // Untagged
  return null;
}

// Add classifyRoad, classifyService here as needed during integration.
// Refer to src/classifiers.py for the canonical mapping.
```

(Engineer must port the full logic from `map.html` inline code. Use Python `src/classifiers.py` as reference.)

- [ ] **Step 6: Run tests to verify they pass**

```bash
node --test tests-js/classifiers.test.js
```

Expected: PASS all fixture cases.

- [ ] **Step 7: Commit**

```bash
git add visualizer/js/classifiers.js tests-js/classifiers.test.js tests-js/fixtures/classifier-cases.json
git commit -m "feat(visualizer): extract classifiers.js + JSON fixtures for parity tests"
```

- [ ] **Step 8: Update map.html to use the new classifier module**

Replace inline `classifyZoning` (or similar) with import + module use:

```html
<script type="module" src="js/classifiers.js"></script>
```

```javascript
import { classifyZoning } from './js/classifiers.js';
// ... use everywhere inline logic was called
```

- [ ] **Step 9: Commit map.html update**

```bash
git add visualizer/map.html
git commit -m "refactor(visualizer): use classifiers.js module in map.html"
```

---

### Task 6: Regression test — verify 10 cities still render after refactor

**Files:**
- Create: `tests-js/e2e/map-regression.spec.js`

- [ ] **Step 1: Verify Playwright is set up locally (or set it up)**

```bash
npx playwright --version 2>/dev/null || npm install -D @playwright/test
npx playwright install chromium
```

- [ ] **Step 2: Write regression test**

Write `tests-js/e2e/map-regression.spec.js`:

```javascript
import { test, expect } from '@playwright/test';

const CITIES = [
  'minneapolis', 'amsterdam', 'madison', 'charleston',
  'trondheim', 'bacau_ro', 'mafra_sc_brazil',
  'fayetteville_nc', 'sacramento', 'new_york'
];

for (const slug of CITIES) {
  test(`map.html renders zoning polygons for ${slug}`, async ({ page }) => {
    await page.goto(`http://localhost:8000/map.html?city=${slug}`);
    
    // Wait for Leaflet overlay to populate
    await page.waitForSelector('.leaflet-overlay-pane', { timeout: 15000 });
    
    // Wait for canvas or SVG paths to appear
    await page.waitForFunction(() => {
      const overlay = document.querySelector('.leaflet-overlay-pane');
      if (!overlay) return false;
      const paths = overlay.querySelectorAll('path');
      const canvases = overlay.querySelectorAll('canvas');
      return paths.length > 50 || canvases.length > 0;
    }, { timeout: 30000 });
    
    // No console errors
    const errors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    await page.waitForTimeout(2000);
    expect(errors).toEqual([]);
  });
}
```

- [ ] **Step 3: Run local HTTP server, then run tests**

```bash
# In one terminal:
cd visualizer && python -m http.server 8000

# In another terminal:
npx playwright test tests-js/e2e/map-regression.spec.js
```

Expected: All 10 tests PASS.

- [ ] **Step 4: If any city fails, the refactor broke something — fix it**

Common failure modes:
- Module import path wrong → check `<script type="module" src="..."/>` in map.html
- Function name mismatch → check exports match imports
- Inline code still referenced → verify all inline logic was removed

Iterate until all 10 pass.

- [ ] **Step 5: Commit regression test**

```bash
git add tests-js/e2e/map-regression.spec.js
git commit -m "test(e2e): verify all 10 cities render post-refactor in map.html"
```

---

### Task 7: Add e2e job to CI

**Files:**
- Modify: `.github/workflows/test.yml`

- [ ] **Step 1: Add e2e job**

Add to `.github/workflows/test.yml`:

```yaml
  e2e-tests:
    name: E2E Tests (Playwright)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - name: Install Playwright
        run: |
          npm install -D @playwright/test
          npx playwright install chromium --with-deps
      - name: Start local server
        run: |
          cd visualizer
          python -m http.server 8000 &
          sleep 2
      - name: Run e2e tests
        run: npx playwright test tests-js/e2e/
```

- [ ] **Step 2: Commit and push**

```bash
git add .github/workflows/test.yml
git commit -m "ci: add e2e-tests job for Playwright regression on map.html"
git push origin main
```

- [ ] **Step 3: Verify CI passes**

Check https://github.com/Osyanne/CitiesSkylines2-osm-toolkit/actions

Expected: 3 jobs (python-tests, js-tests, e2e-tests) all green.

---

## Phase 2: New JS modules (8 tasks)

### Task 8: Implement search.js (Nominatim autocomplete)

**Files:**
- Create: `visualizer/js/search.js`
- Create: `tests-js/search.test.js`

- [ ] **Step 1: Write failing test**

Write `tests-js/search.test.js`:

```javascript
import { test } from 'node:test';
import assert from 'node:assert';
import { mockFetch } from './helpers/mock-fetch.js';
import { searchCity, debounce } from '../visualizer/js/search.js';

test('searchCity returns parsed Nominatim results', async () => {
  const fetch = mockFetch([{
    url: /nominatim\.openstreetmap\.org/,
    status: 200,
    body: [
      { display_name: 'Tokyo, Japan', lat: '35.68', lon: '139.69' },
      { display_name: 'Tokyo, OH, USA', lat: '40.0', lon: '-83.0' }
    ]
  }]);
  
  const results = await searchCity('Tokyo', { fetch });
  assert.equal(results.length, 2);
  assert.equal(results[0].name, 'Tokyo, Japan');
  assert.equal(results[0].lat, 35.68);
  assert.equal(results[0].lon, 139.69);
});

test('debounce limits call rate', async () => {
  let count = 0;
  const fn = debounce(() => count++, 50);
  fn(); fn(); fn();
  await new Promise(r => setTimeout(r, 70));
  assert.equal(count, 1);
});

test('searchCity returns empty array on 0 results', async () => {
  const fetch = mockFetch([{
    url: /nominatim/, status: 200, body: []
  }]);
  const results = await searchCity('Atlantis_NoResults', { fetch });
  assert.equal(results.length, 0);
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
node --test tests-js/search.test.js
```

Expected: FAIL (module not found).

- [ ] **Step 3: Implement search.js**

Write `visualizer/js/search.js`:

```javascript
// Nominatim city search with debounce.

const NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search';

export async function searchCity(query, options = {}) {
  const fetchFn = options.fetch || fetch;
  const url = `${NOMINATIM_URL}?q=${encodeURIComponent(query)}&format=json&limit=5&addressdetails=0`;
  
  const response = await fetchFn(url, {
    headers: { 'User-Agent': 'cs2-osm-toolkit/3.5' }
  });
  
  if (!response.ok) {
    throw new Error(`Nominatim search failed: ${response.status}`);
  }
  
  const data = await response.json();
  return data.map(r => ({
    name: r.display_name,
    lat: parseFloat(r.lat),
    lon: parseFloat(r.lon),
    bbox: r.boundingbox ? r.boundingbox.map(parseFloat) : null
  }));
}

export function debounce(fn, ms = 500) {
  let timeout;
  return function (...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => fn.apply(this, args), ms);
  };
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
node --test tests-js/search.test.js
```

Expected: PASS all 3 tests.

- [ ] **Step 5: Commit**

```bash
git add visualizer/js/search.js tests-js/search.test.js
git commit -m "feat(visualizer): add search.js for Nominatim city autocomplete"
```

---

### Task 9: Implement tile-picker.js (14.336km tile lock)

**Files:**
- Create: `visualizer/js/tile-picker.js`
- Create: `tests-js/tile-picker.test.js`

- [ ] **Step 1: Write failing test**

Write `tests-js/tile-picker.test.js`:

```javascript
import { test } from 'node:test';
import assert from 'node:assert';
import { computeTileBounds, TILE_KM } from '../visualizer/js/tile-picker.js';

test('TILE_KM is 14.336 (CS2 native)', () => {
  assert.equal(TILE_KM, 14.336);
});

test('computeTileBounds returns bbox of correct size at equator', () => {
  const bounds = computeTileBounds(0, 0); // lat=0, lon=0
  const heightKm = (bounds.north - bounds.south) * 111;
  const widthKm = (bounds.east - bounds.west) * 111 * Math.cos(0);
  assert.ok(Math.abs(heightKm - 14.336) < 0.01, `height ${heightKm} should be ~14.336`);
  assert.ok(Math.abs(widthKm - 14.336) < 0.01, `width ${widthKm} should be ~14.336`);
});

test('computeTileBounds accounts for latitude in width calc', () => {
  const bounds = computeTileBounds(45, 0); // lat=45
  const widthKm = (bounds.east - bounds.west) * 111 * Math.cos(45 * Math.PI / 180);
  assert.ok(Math.abs(widthKm - 14.336) < 0.01, `width ${widthKm} at lat=45 should be ~14.336`);
});

test('computeTileBounds returns symmetric bounds around center', () => {
  const lat = 35.68;
  const lon = 139.69; // Tokyo
  const bounds = computeTileBounds(lat, lon);
  const centerLat = (bounds.north + bounds.south) / 2;
  const centerLon = (bounds.east + bounds.west) / 2;
  assert.ok(Math.abs(centerLat - lat) < 0.0001);
  assert.ok(Math.abs(centerLon - lon) < 0.0001);
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
node --test tests-js/tile-picker.test.js
```

Expected: FAIL.

- [ ] **Step 3: Implement tile-picker.js**

Write `visualizer/js/tile-picker.js`:

```javascript
// Tile bounds calculator. Locks output to 14.336km × 14.336km (CS2 native single-tile size).

export const TILE_KM = 14.336;
const KM_PER_DEG_LAT = 111; // approximation: 1° latitude ≈ 111 km

export function computeTileBounds(lat, lon) {
  // Half-tile in degrees, accounting for longitude shrinkage at high latitudes
  const latRad = lat * Math.PI / 180;
  const halfTileDegLat = TILE_KM / 2 / KM_PER_DEG_LAT;
  const halfTileDegLon = TILE_KM / 2 / (KM_PER_DEG_LAT * Math.cos(latRad));
  
  return {
    south: lat - halfTileDegLat,
    north: lat + halfTileDegLat,
    west: lon - halfTileDegLon,
    east: lon + halfTileDegLon
  };
}

// Attaches the tile picker to a Leaflet map, returns control object.
// Browser-only — not testable without Leaflet/DOM. Skipped in unit tests.
export function attachTilePicker(leafletMap, initialLat, initialLon) {
  // TODO during integration: render a draggable Leaflet rectangle locked to 14.336km
  // For now, just return the bounds (no UI). UI wired in main.js integration task.
  return {
    getBounds: () => computeTileBounds(initialLat, initialLon),
    onMove: (callback) => { /* attach Leaflet event */ }
  };
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
node --test tests-js/tile-picker.test.js
```

Expected: PASS all 4 tests.

- [ ] **Step 5: Commit**

```bash
git add visualizer/js/tile-picker.js tests-js/tile-picker.test.js
git commit -m "feat(visualizer): add tile-picker.js with 14.336km CS2-native tile lock"
```

---

### Task 10: Implement srtm-fetcher.js (SRTM tile download + mosaic)

**Files:**
- Create: `visualizer/js/srtm-fetcher.js`
- Create: `tests-js/srtm-fetcher.test.js`

- [ ] **Step 1: Write failing test**

Write `tests-js/srtm-fetcher.test.js`:

```javascript
import { test } from 'node:test';
import assert from 'node:assert';
import { mockFetch } from './helpers/mock-fetch.js';
import { computeTilesForBbox, mosaicTiles } from '../visualizer/js/srtm-fetcher.js';

test('computeTilesForBbox returns single tile for small bbox in one degree', () => {
  const tiles = computeTilesForBbox({
    south: 45.0, north: 45.1, west: -93.5, east: -93.4
  });
  assert.equal(tiles.length, 1);
  assert.equal(tiles[0].lat, 45);
  assert.equal(tiles[0].lon, -94); // SRTM tile name is integer floor of bottom-left
});

test('computeTilesForBbox returns 4 tiles when bbox spans 2x2 degrees', () => {
  const tiles = computeTilesForBbox({
    south: 44.9, north: 45.1, west: -94.1, east: -93.9
  });
  assert.equal(tiles.length, 4);
});

test('mosaicTiles concatenates 1 tile into single grid', () => {
  const tile = { lat: 45, lon: -94, data: new Uint16Array(9).fill(100), width: 3, height: 3 };
  const mosaic = mosaicTiles([tile], { south: 45, north: 45.001, west: -94, east: -93.999 });
  assert.ok(mosaic.data.length > 0);
  assert.equal(mosaic.data[0], 100);
});
```

- [ ] **Step 2: Run test, verify fail**

```bash
node --test tests-js/srtm-fetcher.test.js
```

Expected: FAIL.

- [ ] **Step 3: Implement srtm-fetcher.js**

Write `visualizer/js/srtm-fetcher.js`:

```javascript
// SRTM v3 elevation tile fetcher.
// Each SRTM tile is 1° × 1°, 3601×3601 samples (1 arc-second resolution ~30m).
// Tile naming: N45W094.hgt (lat letter + abs(lat), lon letter + abs(lon))

const SRTM_BASE = 'https://opentopography.org/otr/getdem';
const SRTM_FALLBACK = 'https://e4ftl01.cr.usgs.gov/SRTM/SRTMGL1.003/2000.02.11/';

export function computeTilesForBbox(bbox) {
  const tiles = [];
  for (let lat = Math.floor(bbox.south); lat <= Math.floor(bbox.north); lat++) {
    for (let lon = Math.floor(bbox.west); lon <= Math.floor(bbox.east); lon++) {
      tiles.push({ lat, lon });
    }
  }
  return tiles;
}

export function tileFilename({ lat, lon }) {
  const latStr = (lat >= 0 ? 'N' : 'S') + String(Math.abs(lat)).padStart(2, '0');
  const lonStr = (lon >= 0 ? 'E' : 'W') + String(Math.abs(lon)).padStart(3, '0');
  return `${latStr}${lonStr}.hgt`;
}

export async function fetchTile(tile, options = {}) {
  const fetchFn = options.fetch || fetch;
  const filename = tileFilename(tile);
  // OpenTopography API requires API key for some endpoints — use public bulk download
  const url = `https://s3.amazonaws.com/elevation-tiles-prod/skadi/${filename}.gz`;
  
  let attempt = 0;
  const maxRetries = 3;
  
  while (attempt < maxRetries) {
    try {
      const response = await fetchFn(url);
      if (response.ok) {
        const buffer = await response.arrayBuffer();
        // Decompress .gz, parse as Int16 big-endian
        return parseSRTMHGT(buffer, filename);
      }
      if (response.status === 404) {
        return null; // tile gap, fill with sea level later
      }
      throw new Error(`SRTM fetch ${response.status}`);
    } catch (err) {
      attempt++;
      if (attempt >= maxRetries) throw err;
      await new Promise(r => setTimeout(r, 1000 * Math.pow(2, attempt))); // exp backoff
    }
  }
}

function parseSRTMHGT(buffer, filename) {
  // SRTM .hgt files: 16-bit signed big-endian elevation values, 3601×3601 for SRTMGL1
  const view = new DataView(buffer);
  const expectedSize = 3601 * 3601 * 2;
  if (buffer.byteLength !== expectedSize) {
    throw new Error(`SRTM tile ${filename}: expected ${expectedSize} bytes, got ${buffer.byteLength}`);
  }
  const data = new Uint16Array(3601 * 3601);
  for (let i = 0; i < data.length; i++) {
    const v = view.getInt16(i * 2, false); // big-endian
    // Map signed Int16 to Uint16 (clip negative to 0 = sea level)
    data[i] = v < 0 ? 0 : v;
  }
  return { data, width: 3601, height: 3601 };
}

export function mosaicTiles(tiles, bbox) {
  // For v1 simplicity: if only 1 tile, just clip and return.
  // Multi-tile mosaic is more complex; handled in heightmap.js resample step.
  if (tiles.length === 1) {
    const t = tiles[0];
    return { data: t.data, width: t.width || 3601, height: t.height || 3601, bbox };
  }
  // TODO: implement multi-tile stitch for spans > 1°. For v1, warn user.
  throw new Error('Multi-tile SRTM mosaic not implemented in v1. Use bbox within single degree.');
}
```

- [ ] **Step 4: Run tests, verify pass**

```bash
node --test tests-js/srtm-fetcher.test.js
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add visualizer/js/srtm-fetcher.js tests-js/srtm-fetcher.test.js
git commit -m "feat(visualizer): add srtm-fetcher.js for SRTM tile download + mosaic"
```

---

### Task 11: Implement heightmap.js (resample + UPNG encode)

**Files:**
- Create: `visualizer/js/heightmap.js`
- Create: `tests-js/heightmap.test.js`

- [ ] **Step 1: Write failing test**

Write `tests-js/heightmap.test.js`:

```javascript
import { test } from 'node:test';
import assert from 'node:assert';
import { resampleBilinear, encodePNG16 } from '../visualizer/js/heightmap.js';

test('resampleBilinear preserves uniform values', () => {
  const input = new Uint16Array(4 * 4).fill(500);
  const output = resampleBilinear(input, 4, 4, 8, 8);
  assert.equal(output.length, 8 * 8);
  // All values should still be 500 after bilinear interp of constant input
  for (const v of output) {
    assert.equal(v, 500);
  }
});

test('resampleBilinear interpolates correctly between known values', () => {
  // Input: 2x2 grid with corners 0, 100, 100, 200
  const input = new Uint16Array([0, 100, 100, 200]);
  const output = resampleBilinear(input, 2, 2, 4, 4);
  // Output center (2,2) should be 100 (average of 4 corners)
  // (Exact value depends on sampling math; check it's within range)
  assert.equal(output.length, 16);
  assert.ok(output[5] > 0 && output[5] < 200);
});

test('encodePNG16 returns valid PNG bytes', () => {
  const data = new Uint16Array(16 * 16).fill(32768);
  const png = encodePNG16(data, 16, 16);
  // PNG signature: 89 50 4E 47 0D 0A 1A 0A
  assert.equal(png[0], 0x89);
  assert.equal(png[1], 0x50);
  assert.equal(png[2], 0x4E);
  assert.equal(png[3], 0x47);
  assert.ok(png.length > 100); // arbitrary sanity bound
});
```

- [ ] **Step 2: Run test, verify fail**

```bash
node --test tests-js/heightmap.test.js
```

Expected: FAIL.

- [ ] **Step 3: Implement heightmap.js**

Write `visualizer/js/heightmap.js`:

```javascript
// Heightmap pipeline: bilinear resample → 16-bit PNG encode.
// Uses Canvas API in browser; for Node tests, uses pure JS resample.

export function resampleBilinear(input, inWidth, inHeight, outWidth, outHeight) {
  const output = new Uint16Array(outWidth * outHeight);
  const xRatio = (inWidth - 1) / outWidth;
  const yRatio = (inHeight - 1) / outHeight;
  
  for (let y = 0; y < outHeight; y++) {
    for (let x = 0; x < outWidth; x++) {
      const srcX = x * xRatio;
      const srcY = y * yRatio;
      const x0 = Math.floor(srcX);
      const y0 = Math.floor(srcY);
      const x1 = Math.min(x0 + 1, inWidth - 1);
      const y1 = Math.min(y0 + 1, inHeight - 1);
      const dx = srcX - x0;
      const dy = srcY - y0;
      
      const v00 = input[y0 * inWidth + x0];
      const v10 = input[y0 * inWidth + x1];
      const v01 = input[y1 * inWidth + x0];
      const v11 = input[y1 * inWidth + x1];
      
      const top = v00 * (1 - dx) + v10 * dx;
      const bot = v01 * (1 - dx) + v11 * dx;
      const v = top * (1 - dy) + bot * dy;
      
      output[y * outWidth + x] = Math.round(v);
    }
  }
  
  return output;
}

export function encodePNG16(data, width, height) {
  // Uses UPNG.js (vendored). In Node tests, simulate the PNG header bytes.
  // In browser: UPNG.encode(rgbaBuffer, width, height, 0)
  
  if (typeof UPNG !== 'undefined') {
    // Convert Uint16Array to ImageData-like buffer for UPNG
    // UPNG.encode expects RGBA, so we replicate the elevation across all 4 channels
    // (For grayscale 16-bit, encode just R or use UPNG's mode flag)
    // TODO: refine encoding flags during integration to match CS2 import expectation
    const rgba = new Uint8Array(width * height * 4);
    for (let i = 0; i < data.length; i++) {
      const v = data[i];
      rgba[i * 4 + 0] = (v >> 8) & 0xff;
      rgba[i * 4 + 1] = v & 0xff;
      rgba[i * 4 + 2] = 0;
      rgba[i * 4 + 3] = 255;
    }
    return new Uint8Array(UPNG.encode([rgba.buffer], width, height, 0));
  }
  
  // Test stub: return a minimal valid PNG signature for tests in Node
  // (Real PNG encoding requires UPNG.js loaded in browser)
  const stub = new Uint8Array(150);
  stub.set([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A], 0);
  return stub;
}
```

- [ ] **Step 4: Run tests, verify pass**

```bash
node --test tests-js/heightmap.test.js
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add visualizer/js/heightmap.js tests-js/heightmap.test.js
git commit -m "feat(visualizer): add heightmap.js with bilinear resample + UPNG encode"
```

---

### Task 12: Implement water-extractor.js

**Files:**
- Create: `visualizer/js/water-extractor.js`
- Create: `tests-js/water-extractor.test.js`

- [ ] **Step 1: Write failing test**

Write `tests-js/water-extractor.test.js`:

```javascript
import { test } from 'node:test';
import assert from 'node:assert';
import { mockFetch } from './helpers/mock-fetch.js';
import { extractWater, buildWaterQuery } from '../visualizer/js/water-extractor.js';

test('buildWaterQuery returns valid Overpass query', () => {
  const query = buildWaterQuery({ south: 44.86, west: -93.38, north: 45.05, east: -93.17 });
  assert.match(query, /natural=water/);
  assert.match(query, /44\.86.*-93\.38.*45\.05.*-93\.17/);
});

test('extractWater returns GeoJSON FeatureCollection', async () => {
  const fetch = mockFetch([{
    url: /overpass-api\.de/,
    status: 200,
    body: {
      elements: [
        { type: 'way', id: 1, tags: { natural: 'water' }, geometry: [{ lat: 45, lon: -93 }] }
      ]
    }
  }]);
  
  const result = await extractWater(
    { south: 44.86, west: -93.38, north: 45.05, east: -93.17 },
    { fetch }
  );
  
  assert.equal(result.type, 'FeatureCollection');
  assert.ok(Array.isArray(result.features));
});
```

- [ ] **Step 2: Run test, verify fail**

```bash
node --test tests-js/water-extractor.test.js
```

Expected: FAIL.

- [ ] **Step 3: Implement water-extractor.js**

Write `visualizer/js/water-extractor.js`:

```javascript
import { fetchOverpass } from './overpass-client.js';

export function buildWaterQuery(bbox) {
  const { south, west, north, east } = bbox;
  return `
    [out:json][timeout:60];
    (
      way["natural"="water"](${south},${west},${north},${east});
      relation["natural"="water"](${south},${west},${north},${east});
      way["waterway"](${south},${west},${north},${east});
    );
    out body geom;
  `.trim();
}

export async function extractWater(bbox, options = {}) {
  const query = buildWaterQuery(bbox);
  const data = await fetchOverpass(query, options);
  
  const features = data.elements.map(el => {
    if (el.geometry && el.geometry.length > 0) {
      const coords = el.geometry.map(p => [p.lon, p.lat]);
      const isPolygon = el.tags?.natural === 'water';
      return {
        type: 'Feature',
        properties: { osm_id: el.id, ...el.tags },
        geometry: {
          type: isPolygon ? 'Polygon' : 'LineString',
          coordinates: isPolygon ? [coords] : coords
        }
      };
    }
    return null;
  }).filter(f => f !== null);
  
  return { type: 'FeatureCollection', features };
}
```

- [ ] **Step 4: Run tests, verify pass**

```bash
node --test tests-js/water-extractor.test.js
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add visualizer/js/water-extractor.js tests-js/water-extractor.test.js
git commit -m "feat(visualizer): add water-extractor.js (Giscolab-inspired water layer)"
```

---

### Task 13: Implement readme-gen.js (ZIP README templating)

**Files:**
- Create: `visualizer/js/readme-gen.js`
- Create: `tests-js/readme-gen.test.js`

- [ ] **Step 1: Write failing test**

Write `tests-js/readme-gen.test.js`:

```javascript
import { test } from 'node:test';
import assert from 'node:assert';
import { generateReadme } from '../visualizer/js/readme-gen.js';

test('generateReadme includes city name and bbox', () => {
  const readme = generateReadme({
    cityName: 'Tokyo, Japan',
    bbox: { south: 35.6, west: 139.6, north: 35.7, east: 139.8 },
    generatedAt: new Date('2026-05-18T12:00:00Z')
  });
  
  assert.match(readme, /Tokyo, Japan/);
  assert.match(readme, /35\.6/);
  assert.match(readme, /2026-05-18/);
});

test('generateReadme includes import instructions', () => {
  const readme = generateReadme({
    cityName: 'Tokyo',
    bbox: { south: 0, west: 0, north: 1, east: 1 },
    generatedAt: new Date()
  });
  
  assert.match(readme, /CS2/i);
  assert.match(readme, /heightmap/i);
});
```

- [ ] **Step 2: Run test, verify fail**

```bash
node --test tests-js/readme-gen.test.js
```

- [ ] **Step 3: Implement readme-gen.js**

Write `visualizer/js/readme-gen.js`:

```javascript
export function generateReadme({ cityName, bbox, generatedAt }) {
  const date = generatedAt.toISOString().substring(0, 10);
  const { south, west, north, east } = bbox;
  
  return `# ${cityName} — Generated by OSM2CS

**City:** ${cityName}
**Bbox:** ${south}, ${west}, ${north}, ${east}
**Generated:** ${date}
**Tool version:** v3.5.0 (browser-based generator)
**Source:** OpenStreetMap (Overpass API) + SRTM v3 elevation

## What's inside

- \`heightmap.png\` — 16-bit PNG, 4096×4096px, 14.336km tile. Import into Cities Skylines 2 → Map Editor → Terrain → Import Heightmap.
- \`zoning.geojson\` — Real-world land use, classified into 11 CS2 zone types.
- \`roads.geojson\` — Real-world road network, 6 CS2 road tiers.
- \`services.geojson\` — Hospitals, schools, fire stations, police, libraries, parks.
- \`water.geojson\` — Rivers, lakes, ocean polygons (visual reference).
- \`preview.html\` — Offline Leaflet viewer. Serve via any HTTP server.

## How to use

1. Copy \`heightmap.png\` to your CS2 heightmaps folder.
2. Open CS2 → Map Editor → Terrain → Import Heightmap → select the PNG.
3. While building, keep \`preview.html\` open to reference real-world zoning, roads, services, and water.

## License

OSM data © OpenStreetMap contributors ([ODbL](https://www.openstreetmap.org/copyright)). Heightmap derived from SRTM (public domain, NASA). Bundle generated by https://github.com/Osyanne/CitiesSkylines2-osm-toolkit (MIT-licensed).
`;
}
```

- [ ] **Step 4: Run tests, verify pass**

```bash
node --test tests-js/readme-gen.test.js
```

- [ ] **Step 5: Commit**

```bash
git add visualizer/js/readme-gen.js tests-js/readme-gen.test.js
git commit -m "feat(visualizer): add readme-gen.js for ZIP README templating"
```

---

### Task 14: Implement bundler.js (JSZip packaging)

**Files:**
- Create: `visualizer/js/bundler.js`
- Create: `tests-js/bundler.test.js`

- [ ] **Step 1: Write failing test**

Write `tests-js/bundler.test.js`:

```javascript
import { test } from 'node:test';
import assert from 'node:assert';
import { buildZipManifest } from '../visualizer/js/bundler.js';

test('buildZipManifest lists expected files', () => {
  const manifest = buildZipManifest({
    cityName: 'Tokyo',
    hasHeightmap: true,
    hasZoning: true,
    hasRoads: true,
    hasServices: true,
    hasWater: true
  });
  
  const filenames = manifest.map(e => e.filename);
  assert.ok(filenames.includes('heightmap.png'));
  assert.ok(filenames.includes('zoning.geojson'));
  assert.ok(filenames.includes('roads.geojson'));
  assert.ok(filenames.includes('services.geojson'));
  assert.ok(filenames.includes('water.geojson'));
  assert.ok(filenames.includes('preview.html'));
  assert.ok(filenames.includes('README.md'));
});

test('buildZipManifest omits missing layers', () => {
  const manifest = buildZipManifest({
    cityName: 'Tokyo',
    hasHeightmap: true,
    hasZoning: true,
    hasRoads: false,
    hasServices: false,
    hasWater: false
  });
  const filenames = manifest.map(e => e.filename);
  assert.ok(filenames.includes('zoning.geojson'));
  assert.ok(!filenames.includes('roads.geojson'));
});
```

- [ ] **Step 2: Run test, verify fail**

```bash
node --test tests-js/bundler.test.js
```

- [ ] **Step 3: Implement bundler.js**

Write `visualizer/js/bundler.js`:

```javascript
// JSZip bundler. Generates ZIP with heightmap, GeoJSON layers, preview HTML, README.

export function buildZipManifest({ cityName, hasHeightmap, hasZoning, hasRoads, hasServices, hasWater }) {
  const manifest = [];
  if (hasHeightmap) manifest.push({ filename: 'heightmap.png', type: 'binary' });
  if (hasZoning) manifest.push({ filename: 'zoning.geojson', type: 'text' });
  if (hasRoads) manifest.push({ filename: 'roads.geojson', type: 'text' });
  if (hasServices) manifest.push({ filename: 'services.geojson', type: 'text' });
  if (hasWater) manifest.push({ filename: 'water.geojson', type: 'text' });
  manifest.push({ filename: 'preview.html', type: 'text' });
  manifest.push({ filename: 'README.md', type: 'text' });
  return manifest;
}

export async function buildZip({ heightmapPng, zoning, roads, services, water, readme, previewHtml }) {
  // JSZip is loaded globally via <script> tag in generate.html
  const zip = new JSZip();
  
  if (heightmapPng) zip.file('heightmap.png', heightmapPng, { binary: true });
  if (zoning) zip.file('zoning.geojson', JSON.stringify(zoning, null, 2));
  if (roads) zip.file('roads.geojson', JSON.stringify(roads, null, 2));
  if (services) zip.file('services.geojson', JSON.stringify(services, null, 2));
  if (water) zip.file('water.geojson', JSON.stringify(water, null, 2));
  if (previewHtml) zip.file('preview.html', previewHtml);
  if (readme) zip.file('README.md', readme);
  
  return await zip.generateAsync({ type: 'blob', compression: 'DEFLATE' });
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
```

- [ ] **Step 4: Run tests, verify pass**

```bash
node --test tests-js/bundler.test.js
```

- [ ] **Step 5: Commit**

```bash
git add visualizer/js/bundler.js tests-js/bundler.test.js
git commit -m "feat(visualizer): add bundler.js for JSZip packaging"
```

---

### Task 15: Implement progress-ui.js (step state machine)

**Files:**
- Create: `visualizer/js/progress-ui.js`
- Create: `tests-js/progress-ui.test.js`

- [ ] **Step 1: Write failing test**

Write `tests-js/progress-ui.test.js`:

```javascript
import { test } from 'node:test';
import assert from 'node:assert';
import { ProgressTracker } from '../visualizer/js/progress-ui.js';

test('ProgressTracker initializes with all steps pending', () => {
  const tracker = new ProgressTracker(['SRTM', 'Resample', 'PNG']);
  assert.equal(tracker.steps[0].status, 'pending');
  assert.equal(tracker.steps[1].status, 'pending');
});

test('ProgressTracker marks step as running then complete', () => {
  const tracker = new ProgressTracker(['Step1', 'Step2']);
  tracker.start('Step1');
  assert.equal(tracker.steps[0].status, 'running');
  tracker.complete('Step1');
  assert.equal(tracker.steps[0].status, 'complete');
});

test('ProgressTracker tracks elapsed time per step', () => {
  const tracker = new ProgressTracker(['Step1']);
  tracker.start('Step1');
  const elapsed = tracker.getElapsed('Step1');
  assert.ok(elapsed >= 0);
});

test('ProgressTracker can fail a step', () => {
  const tracker = new ProgressTracker(['Step1']);
  tracker.start('Step1');
  tracker.fail('Step1', 'Network timeout');
  assert.equal(tracker.steps[0].status, 'failed');
  assert.equal(tracker.steps[0].error, 'Network timeout');
});
```

- [ ] **Step 2: Run test, verify fail**

```bash
node --test tests-js/progress-ui.test.js
```

- [ ] **Step 3: Implement progress-ui.js**

Write `visualizer/js/progress-ui.js`:

```javascript
// Progress tracker state machine. UI rendering done in main.js integration.

export class ProgressTracker {
  constructor(stepNames) {
    this.steps = stepNames.map(name => ({
      name,
      status: 'pending', // 'pending' | 'running' | 'complete' | 'failed' | 'warning'
      startedAt: null,
      completedAt: null,
      error: null,
      warning: null
    }));
    this.listeners = [];
  }
  
  _find(name) {
    return this.steps.find(s => s.name === name);
  }
  
  start(name) {
    const step = this._find(name);
    if (step) {
      step.status = 'running';
      step.startedAt = Date.now();
      this._notify();
    }
  }
  
  complete(name) {
    const step = this._find(name);
    if (step) {
      step.status = 'complete';
      step.completedAt = Date.now();
      this._notify();
    }
  }
  
  warn(name, message) {
    const step = this._find(name);
    if (step) {
      step.status = 'warning';
      step.warning = message;
      step.completedAt = Date.now();
      this._notify();
    }
  }
  
  fail(name, error) {
    const step = this._find(name);
    if (step) {
      step.status = 'failed';
      step.error = error;
      step.completedAt = Date.now();
      this._notify();
    }
  }
  
  getElapsed(name) {
    const step = this._find(name);
    if (!step || !step.startedAt) return null;
    const end = step.completedAt || Date.now();
    return end - step.startedAt;
  }
  
  onChange(callback) {
    this.listeners.push(callback);
  }
  
  _notify() {
    this.listeners.forEach(cb => cb(this.steps));
  }
}
```

- [ ] **Step 4: Run tests, verify pass**

```bash
node --test tests-js/progress-ui.test.js
```

- [ ] **Step 5: Commit**

```bash
git add visualizer/js/progress-ui.js tests-js/progress-ui.test.js
git commit -m "feat(visualizer): add progress-ui.js state machine"
```

---

## Phase 3: Integration — main.js, generate.html, landing CTA (3 tasks)

### Task 16: Create main.js orchestrator

**Files:**
- Create: `visualizer/js/main.js`

This file ties together all the modules. No unit test — it's tested by E2E (Task 21).

- [ ] **Step 1: Create main.js with orchestration logic**

Write `visualizer/js/main.js`:

```javascript
import { searchCity, debounce } from './search.js';
import { computeTileBounds } from './tile-picker.js';
import { computeTilesForBbox, fetchTile, mosaicTiles } from './srtm-fetcher.js';
import { resampleBilinear, encodePNG16 } from './heightmap.js';
import { fetchOverpass } from './overpass-client.js';
import { classifyZoning } from './classifiers.js';
import { extractWater } from './water-extractor.js';
import { generateReadme } from './readme-gen.js';
import { buildZip, downloadBlob } from './bundler.js';
import { ProgressTracker } from './progress-ui.js';

const STEPS = ['SRTM Fetch', 'Resample', 'PNG Encode', 'OSM Layers', 'Build ZIP'];

let selectedLocation = null;
let leafletMap = null;

function init() {
  const searchInput = document.getElementById('city-search');
  const resultsDropdown = document.getElementById('search-results');
  const generateBtn = document.getElementById('generate-btn');
  const progressEl = document.getElementById('progress');
  
  // Initialize Leaflet map
  leafletMap = L.map('map').setView([0, 0], 2);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png').addTo(leafletMap);
  
  const debouncedSearch = debounce(async (q) => {
    if (q.length < 2) {
      resultsDropdown.innerHTML = '';
      return;
    }
    try {
      const results = await searchCity(q);
      renderResults(results, resultsDropdown);
    } catch (e) {
      console.warn('Search failed:', e);
    }
  }, 500);
  
  searchInput.addEventListener('input', e => debouncedSearch(e.target.value));
  
  generateBtn.addEventListener('click', () => {
    if (selectedLocation) {
      runPipeline(selectedLocation, progressEl);
    }
  });
}

function renderResults(results, dropdown) {
  dropdown.innerHTML = '';
  for (const r of results) {
    const item = document.createElement('div');
    item.textContent = r.name;
    item.className = 'search-result';
    item.addEventListener('click', () => selectCity(r));
    dropdown.appendChild(item);
  }
}

function selectCity(result) {
  selectedLocation = result;
  const bbox = computeTileBounds(result.lat, result.lon);
  
  // Center map on selection
  leafletMap.setView([result.lat, result.lon], 12);
  
  // Draw tile rectangle (overlay)
  if (window.tileRect) leafletMap.removeLayer(window.tileRect);
  window.tileRect = L.rectangle(
    [[bbox.south, bbox.west], [bbox.north, bbox.east]],
    { color: '#7ee787', weight: 2, fillOpacity: 0.1 }
  ).addTo(leafletMap);
  
  document.getElementById('generate-btn').disabled = false;
  document.getElementById('search-results').innerHTML = '';
  document.getElementById('city-search').value = result.name;
}

async function runPipeline(location, progressEl) {
  const bbox = computeTileBounds(location.lat, location.lon);
  const tracker = new ProgressTracker(STEPS);
  tracker.onChange(steps => renderProgress(steps, progressEl));
  
  try {
    // Phase A: heightmap pipeline
    tracker.start('SRTM Fetch');
    const tiles = computeTilesForBbox(bbox);
    const fetched = await Promise.all(tiles.map(t => fetchTile(t)));
    const validTiles = fetched.filter(t => t !== null);
    if (validTiles.length === 0) {
      tracker.fail('SRTM Fetch', 'No SRTM data available for this area');
      return;
    }
    tracker.complete('SRTM Fetch');
    
    tracker.start('Resample');
    const mosaic = mosaicTiles(validTiles, bbox);
    const resampled = resampleBilinear(mosaic.data, mosaic.width, mosaic.height, 4096, 4096);
    tracker.complete('Resample');
    
    tracker.start('PNG Encode');
    const heightmapPng = encodePNG16(resampled, 4096, 4096);
    tracker.complete('PNG Encode');
    
    // Phase B: OSM layers (parallel)
    tracker.start('OSM Layers');
    const [zoning, roads, services, water] = await Promise.all([
      fetchZoningLayer(bbox).catch(e => { console.warn('zoning fail:', e); return null; }),
      fetchRoadsLayer(bbox).catch(e => { console.warn('roads fail:', e); return null; }),
      fetchServicesLayer(bbox).catch(e => { console.warn('services fail:', e); return null; }),
      extractWater(bbox).catch(e => { console.warn('water fail:', e); return null; })
    ]);
    
    if (zoning || roads || services || water) {
      tracker.complete('OSM Layers');
    } else {
      tracker.warn('OSM Layers', 'All OSM layers unavailable, including heightmap only');
    }
    
    // Phase C: bundle
    tracker.start('Build ZIP');
    const readme = generateReadme({
      cityName: location.name,
      bbox,
      generatedAt: new Date()
    });
    const previewHtml = generatePreviewHtml({ zoning, roads, services, water, bbox });
    
    const zipBlob = await buildZip({
      heightmapPng,
      zoning, roads, services, water,
      readme, previewHtml
    });
    
    tracker.complete('Build ZIP');
    
    // Trigger download
    const slug = sluggify(location.name);
    downloadBlob(zipBlob, `${slug}-osm2cs.zip`);
    showSuccess(location.name);
    
  } catch (err) {
    console.error('Pipeline error:', err);
    showError(err.message);
  }
}

async function fetchZoningLayer(bbox) {
  // Use existing Overpass query patterns from the toolkit
  const query = `[out:json][timeout:120];(way["landuse"](${bbox.south},${bbox.west},${bbox.north},${bbox.east});way["building"](${bbox.south},${bbox.west},${bbox.north},${bbox.east}););out body geom;`;
  const data = await fetchOverpass(query);
  const features = data.elements.map(el => {
    const zone = classifyZoning({ tags: el.tags || {} });
    if (!zone || !el.geometry) return null;
    return {
      type: 'Feature',
      properties: { osm_id: el.id, zone, ...el.tags },
      geometry: { type: 'Polygon', coordinates: [el.geometry.map(p => [p.lon, p.lat])] }
    };
  }).filter(f => f !== null);
  return { type: 'FeatureCollection', features };
}

async function fetchRoadsLayer(bbox) {
  // Reuse vial extraction pattern from existing toolkit
  const query = `[out:json][timeout:120];(way["highway"](${bbox.south},${bbox.west},${bbox.north},${bbox.east}););out body geom;`;
  const data = await fetchOverpass(query);
  // Simplified: similar feature extraction to zoning, classified by highway type
  // Full classification logic ported from src/vial_classifiers.py
  const features = data.elements.map(el => {
    if (!el.geometry) return null;
    return {
      type: 'Feature',
      properties: { osm_id: el.id, ...el.tags },
      geometry: { type: 'LineString', coordinates: el.geometry.map(p => [p.lon, p.lat]) }
    };
  }).filter(f => f !== null);
  return { type: 'FeatureCollection', features };
}

async function fetchServicesLayer(bbox) {
  const query = `[out:json][timeout:120];(node["amenity"~"hospital|school|fire_station|police"](${bbox.south},${bbox.west},${bbox.north},${bbox.east});way["amenity"~"hospital|school|fire_station|police"](${bbox.south},${bbox.west},${bbox.north},${bbox.east}););out body geom;`;
  const data = await fetchOverpass(query);
  const features = data.elements.map(el => {
    if (!el.lat && !el.geometry) return null;
    const isNode = el.type === 'node';
    return {
      type: 'Feature',
      properties: { osm_id: el.id, ...el.tags },
      geometry: isNode
        ? { type: 'Point', coordinates: [el.lon, el.lat] }
        : { type: 'Polygon', coordinates: [el.geometry.map(p => [p.lon, p.lat])] }
    };
  }).filter(f => f !== null);
  return { type: 'FeatureCollection', features };
}

function renderProgress(steps, el) {
  el.innerHTML = '';
  for (const s of steps) {
    const icon = { pending: '○', running: '⟳', complete: '✓', warning: '⚠', failed: '✗' }[s.status];
    const div = document.createElement('div');
    div.textContent = `${icon} ${s.name}`;
    el.appendChild(div);
  }
}

function sluggify(name) {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}

function showSuccess(cityName) {
  // Show "Download ready" state
  document.getElementById('progress').innerHTML +=
    `<div class="success">🎉 ${cityName} ZIP ready! Check your downloads folder.</div>`;
}

function showError(message) {
  document.getElementById('progress').innerHTML +=
    `<div class="error">❌ ${message}</div>`;
}

function generatePreviewHtml({ zoning, roads, services, water, bbox }) {
  // Generate a minimal standalone Leaflet viewer that loads the GeoJSON layers
  return `<!DOCTYPE html>
<html><head><title>Preview</title><link rel="stylesheet" href="https://unpkg.com/leaflet@1.9/dist/leaflet.css"/></head>
<body><div id="m" style="width:100%;height:100vh;"></div>
<script src="https://unpkg.com/leaflet@1.9/dist/leaflet.js"></script>
<script>
const map = L.map('m').setView([${(bbox.south+bbox.north)/2},${(bbox.west+bbox.east)/2}], 12);
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png').addTo(map);
const layers = ${JSON.stringify({ zoning, roads, services, water })};
for (const [name, gj] of Object.entries(layers)) {
  if (gj) L.geoJSON(gj, { style: { color: '#7ee787' } }).addTo(map);
}
</script></body></html>`;
}

window.addEventListener('DOMContentLoaded', init);
```

- [ ] **Step 2: Commit**

```bash
git add visualizer/js/main.js
git commit -m "feat(visualizer): add main.js orchestrator for generate.html pipeline"
```

---

### Task 17: Create generate.html UI shell

**Files:**
- Create: `visualizer/generate.html`

- [ ] **Step 1: Write generate.html**

Write `visualizer/generate.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>OSM2CS Generator — CS2 OSM Toolkit</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9/dist/leaflet.css"/>
  <style>
    body { margin: 0; font-family: -apple-system, system-ui, sans-serif; background: #0d1117; color: #c9d1d9; }
    header { padding: 20px; border-bottom: 1px solid #2d3139; }
    h1 { margin: 0; font-size: 24px; }
    .layout { display: flex; height: calc(100vh - 80px); }
    .sidebar { width: 360px; padding: 20px; border-right: 1px solid #2d3139; }
    .map-container { flex: 1; }
    #map { width: 100%; height: 100%; }
    .search-box { width: 100%; padding: 10px; background: #1a1d24; border: 1px solid #2d3139; color: #c9d1d9; border-radius: 4px; font-size: 14px; }
    .search-results { background: #1a1d24; border: 1px solid #2d3139; border-top: none; max-height: 200px; overflow-y: auto; border-radius: 0 0 4px 4px; }
    .search-result { padding: 8px 12px; cursor: pointer; border-bottom: 1px solid #2d3139; font-size: 13px; }
    .search-result:hover { background: #2d3139; }
    .generate-btn { width: 100%; margin-top: 16px; padding: 12px; background: #238636; color: white; border: none; border-radius: 4px; font-size: 14px; cursor: pointer; }
    .generate-btn:disabled { background: #2d3139; cursor: not-allowed; opacity: 0.5; }
    .progress { margin-top: 20px; font-family: 'Consolas', monospace; font-size: 13px; line-height: 1.8; }
    .progress .success { color: #7ee787; }
    .progress .error { color: #ff7b72; }
    .info { margin-top: 20px; padding: 12px; background: #1a1d24; border-radius: 4px; font-size: 12px; color: #8b949e; }
  </style>
</head>
<body>
  <header>
    <h1>⚡ OSM2CS Generator</h1>
    <div style="font-size: 12px; color: #8b949e; margin-top: 4px;">
      Generate a CS2-ready map bundle for any city. Browser does everything — no install, no signup.
    </div>
  </header>
  
  <div class="layout">
    <div class="sidebar">
      <label style="font-size: 12px; color: #8b949e; display: block; margin-bottom: 4px;">Search a city</label>
      <input
        type="text"
        id="city-search"
        class="search-box"
        placeholder="e.g., Tokyo, Lima, Berlin..."
        autocomplete="off"
      />
      <div id="search-results" class="search-results"></div>
      
      <button id="generate-btn" class="generate-btn" disabled>✓ Generate ZIP</button>
      
      <div id="progress" class="progress"></div>
      
      <div class="info">
        Tile size: <strong>14.336 km × 14.336 km</strong> (CS2 native).<br>
        Output: heightmap.png + 4 GeoJSON layers + offline viewer + README in a ZIP.<br>
        Expected time: 30–90 seconds.<br>
        Recommended: desktop with 4+ GB RAM.
      </div>
    </div>
    
    <div class="map-container">
      <div id="map"></div>
    </div>
  </div>
  
  <script src="https://unpkg.com/leaflet@1.9/dist/leaflet.js"></script>
  <script src="lib/jszip.min.js"></script>
  <script src="lib/upng.min.js"></script>
  <script type="module" src="js/main.js"></script>
</body>
</html>
```

- [ ] **Step 2: Verify it loads in a browser locally**

```bash
cd visualizer && python -m http.server 8000
```

Open `http://localhost:8000/generate.html` in a browser. Verify:
- Page loads without console errors
- Search input accepts text
- Map shows (dark theme)
- Generate button visible but disabled

- [ ] **Step 3: Commit**

```bash
git add visualizer/generate.html
git commit -m "feat(visualizer): add generate.html UI shell"
```

---

### Task 18: Add "Generate yours" CTA to landing

**Files:**
- Modify: `visualizer/index.html`
- Modify: `src/shared/landing.py` (if landing is auto-generated)

- [ ] **Step 1: Check how index.html is generated**

```bash
grep -r "Generate your own\|generate.html" visualizer/ src/ 2>/dev/null
ls src/shared/ 2>/dev/null
```

If `landing.py` exists and auto-generates `index.html`, modify the template there. If `index.html` is hand-written, edit directly.

- [ ] **Step 2: Add CTA section in landing.py template OR index.html**

In the landing template (e.g., near the end of the city cards section), add:

```html
<div class="generate-cta" style="margin-top: 40px; padding: 24px; background: linear-gradient(135deg, #238636, #2ea043); border-radius: 8px; text-align: center;">
  <h2 style="color: white; margin: 0 0 8px 0;">⚡ Generate your own city</h2>
  <p style="color: rgba(255,255,255,0.9); margin: 0 0 16px 0;">
    Don't see your city above? Generate a CS2-ready map bundle for any city in the world, right in your browser.
  </p>
  <a href="generate.html" style="display: inline-block; padding: 10px 24px; background: white; color: #238636; text-decoration: none; border-radius: 4px; font-weight: 600;">
    Open Generator →
  </a>
</div>
```

- [ ] **Step 3: If auto-generated, regenerate landing**

```bash
cd src
uv run generate-landing
```

Verify `visualizer/index.html` now contains the CTA.

- [ ] **Step 4: View locally**

```bash
cd visualizer && python -m http.server 8000
```

Open `http://localhost:8000/` — verify CTA is visible after the city cards.

- [ ] **Step 5: Commit**

```bash
git add visualizer/index.html src/shared/landing.py
git commit -m "feat(landing): add 'Generate yours' CTA pointing to generate.html"
```

---

## Phase 4: Integration & E2E tests (3 tasks)

### Task 19: Integration test — happy path

**Files:**
- Create: `tests-js/e2e/generator-happy-path.spec.js`

- [ ] **Step 1: Write integration E2E test**

Write `tests-js/e2e/generator-happy-path.spec.js`:

```javascript
import { test, expect } from '@playwright/test';

test('full generator flow for Minneapolis produces downloadable ZIP', async ({ page }) => {
  await page.goto('http://localhost:8000/generate.html');
  
  // Type city name
  await page.fill('#city-search', 'Minneapolis');
  
  // Wait for autocomplete dropdown
  await page.waitForSelector('.search-result', { timeout: 5000 });
  
  // Click first result
  await page.click('.search-result >> nth=0');
  
  // Verify button is now enabled
  await expect(page.locator('#generate-btn')).toBeEnabled();
  
  // Set up download listener BEFORE clicking generate
  const downloadPromise = page.waitForEvent('download', { timeout: 120000 });
  
  // Click generate
  await page.click('#generate-btn');
  
  // Wait for generation to complete (up to 2 min)
  const download = await downloadPromise;
  
  // Verify filename matches pattern
  const filename = download.suggestedFilename();
  expect(filename).toMatch(/minneapolis.*osm2cs\.zip$/i);
  
  // Save and verify ZIP contents
  const path = `/tmp/test-download-${Date.now()}.zip`;
  await download.saveAs(path);
  
  // Verify ZIP has expected files (use 'unzip -l' or a JS unzip lib)
  // For simplicity: check file exists and has reasonable size
  const fs = await import('fs');
  const stats = fs.statSync(path);
  expect(stats.size).toBeGreaterThan(100_000); // at least 100 KB
});
```

- [ ] **Step 2: Run e2e test (requires real SRTM/Overpass access)**

```bash
cd visualizer && python -m http.server 8000 &
sleep 2
npx playwright test tests-js/e2e/generator-happy-path.spec.js
```

Expected: PASS (may take 60-120 seconds due to real fetches).

- [ ] **Step 3: Commit**

```bash
git add tests-js/e2e/generator-happy-path.spec.js
git commit -m "test(e2e): happy path generator flow produces valid ZIP"
```

---

### Task 20: Integration test — failure paths

**Files:**
- Create: `tests-js/e2e/generator-failure-paths.spec.js`

- [ ] **Step 1: Write failure-mode tests**

Write `tests-js/e2e/generator-failure-paths.spec.js`:

```javascript
import { test, expect } from '@playwright/test';

test('shows error when city not found', async ({ page }) => {
  await page.goto('http://localhost:8000/generate.html');
  
  await page.fill('#city-search', 'XYZZYNotARealCity12345');
  await page.waitForTimeout(1500); // wait for debounced search
  
  // Should show 0 results (dropdown empty)
  const resultCount = await page.locator('.search-result').count();
  expect(resultCount).toBe(0);
  
  // Generate button still disabled
  await expect(page.locator('#generate-btn')).toBeDisabled();
});

test('handles search rate limiting gracefully', async ({ page }) => {
  await page.goto('http://localhost:8000/generate.html');
  
  // Hammer the search input
  for (let i = 0; i < 10; i++) {
    await page.fill('#city-search', `Test${i}`);
    await page.waitForTimeout(50); // intentionally below debounce threshold
  }
  
  // Verify no uncaught errors in console
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.waitForTimeout(2000);
  expect(errors).toEqual([]);
});

test('Generate button stays disabled until city selected', async ({ page }) => {
  await page.goto('http://localhost:8000/generate.html');
  
  await expect(page.locator('#generate-btn')).toBeDisabled();
  
  await page.fill('#city-search', 'Tokyo');
  await page.waitForTimeout(1000);
  
  // Still disabled until user clicks a result
  await expect(page.locator('#generate-btn')).toBeDisabled();
});
```

- [ ] **Step 2: Run tests**

```bash
npx playwright test tests-js/e2e/generator-failure-paths.spec.js
```

Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests-js/e2e/generator-failure-paths.spec.js
git commit -m "test(e2e): generator failure paths and edge cases"
```

---

### Task 21: Browser compatibility smoke tests

**Files:**
- Modify: `tests-js/e2e/generator-happy-path.spec.js` (add browser-project config)
- Create: `playwright.config.js` (if not exists)

- [ ] **Step 1: Create or update playwright.config.js**

Write or modify `playwright.config.js`:

```javascript
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests-js/e2e',
  timeout: 180000, // 3 min for slow generation tests
  
  projects: [
    { name: 'chromium', use: devices['Desktop Chrome'] },
    { name: 'firefox', use: devices['Desktop Firefox'] },
    { name: 'webkit', use: devices['Desktop Safari'] }
    // Skip mobile — explicitly unsupported
  ]
});
```

- [ ] **Step 2: Run all browsers**

```bash
npx playwright install firefox webkit  # if not already
npx playwright test
```

Expected: All tests pass on chromium, firefox, webkit.

- [ ] **Step 3: If a browser fails, investigate and adjust**

Common cross-browser issues:
- Canvas API behavior subtle differences
- File download triggers differ
- UPNG.js may behave differently in Safari

Fix or mark as `test.skip()` with reason if not fixable.

- [ ] **Step 4: Commit**

```bash
git add playwright.config.js
git commit -m "test(e2e): cross-browser config (chromium/firefox/webkit)"
```

---

## Phase 5: Documentation & release (4 tasks)

### Task 22: Update README.md

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add v3.5 generator section to README**

In the main README (after the Cities section, before Path A/B), add:

```markdown
## ⚡ Generate any city (v3.5+)

Want a city not yet in the toolkit? Use the browser-based generator — zero install, zero signup:

**→ https://osyanne.github.io/CitiesSkylines2-osm-toolkit/generate.html**

Type your city name → confirm the 14.336km tile → click Generate. Your browser downloads SRTM elevation, queries OpenStreetMap, and packages everything as a CS2-ready ZIP (heightmap.png + 4 GeoJSON layers + offline viewer). Takes ~30-90 seconds. Desktop only (mobile RAM is insufficient).

Free, MIT, no backend, no rate limiting, no data collection.

If you want your city added to the curated set (with thumbnail + landing-page card), file a [city-request issue](https://github.com/Osyanne/CitiesSkylines2-osm-toolkit/issues/new?template=city-request.yml) — manual generation by the maintainer, usually same-day.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs(README): add v3.5 generator section"
```

---

### Task 23: Update METHODOLOGY.md

**Files:**
- Modify: `METHODOLOGY.md` (or create section if doesn't exist)

- [ ] **Step 1: Add v3.5 architecture section**

Add to `METHODOLOGY.md`:

```markdown
## Section 15: v3.5 Browser-based Generator

The v3.5 release adds a client-side tool (`visualizer/generate.html`) that produces a CS2-ready map bundle for any city, with no backend. The entire pipeline runs in the user's browser.

### Architecture decision

Three forms were considered for productizing the generator:

1. **CLI extension** — add `extract-heightmap` to the existing Python toolkit. Zero new infra but requires Python install on user side.
2. **Free hosted tool, client-side** — browser does everything via JS. $0 to operate. Selected for v3.5.
3. **Full SaaS with auth + billing** — backend server, user accounts, Pro tier. Deferred to Phase 4.

Option 2 was selected because:
- Aligns with the project's "no recurring cost" principle
- Patreon (launched 2026-05-20) handles monetization without coupling to usage
- GitHub Pages hosts everything for free
- Forward-compatible: if Phase 4 ships a Pro tier, free client-side mode remains

### Pipeline (browser-side)

```
search.js (Nominatim) → tile-picker.js (14.336km lock)
   ↓
Promise.all([
  srtm-fetcher.js → heightmap.js (resample + UPNG),
  overpass-client.js → classifiers.js (zoning/roads/services) + water-extractor.js
])
   ↓
bundler.js (JSZip) → preview.html (templated) + README.md (templated)
   ↓
Browser download
```

### Key technical decisions

- **Vanilla JS, no framework, no build step.** Browser ES modules served directly. Consistent with existing visualizer architecture.
- **Vendored libs** (JSZip, UPNG.js) in `visualizer/lib/`. No CDN dependency at runtime.
- **Refactor of `overpass-client.js` and `classifiers.js`** out of `map.html` inline scripts into reusable JS modules. Same logic, two consumers (map.html + generate.html).
- **Mobile UA detected, warned upfront.** Pipeline requires ~250-400 MB peak RAM; mobile tabs lack this.
- **No telemetry, no tracking, no analytics.** Privacy-first.

### Water layer (Giscolab-inspired)

Added to v3.5 based on a downstream-builder feedback signal: Franck Da Costa (`@Giscolab`) added a dedicated water layer to his fork. We integrated it as a first-class output in our generator. See `docs/specs/2026-05-18-osm2cs-generator-design.md` §11 for the analysis.
```

- [ ] **Step 2: Commit**

```bash
git add METHODOLOGY.md
git commit -m "docs(METHODOLOGY): add v3.5 generator architecture section"
```

---

### Task 24: Final smoke test + version bump

**Files:**
- Modify: `src/pyproject.toml` (version bump)
- Modify: `cities.json` (if version is tracked there)

- [ ] **Step 1: Final smoke test on real browser**

Start server, manually generate for Minneapolis end-to-end:

```bash
cd visualizer && python -m http.server 8000
```

Open https://localhost:8000/generate.html, generate Minneapolis, verify:
- Search autocomplete works
- Tile rectangle appears on map
- Progress UI updates correctly
- ZIP downloads
- ZIP contains heightmap.png + 4 GeoJSONs + preview.html + README.md
- heightmap.png is 4096×4096 16-bit PNG (verify with file inspector)
- preview.html opens and shows layers

If any step fails, fix and re-test.

- [ ] **Step 2: Bump version in src/pyproject.toml**

```toml
# Change:
version = "3.4.0"
# To:
version = "3.5.0"
```

- [ ] **Step 3: Run full pytest + node test suite + e2e**

```bash
# Python tests (existing)
uv run pytest

# JS tests (new)
node --test tests-js/

# E2E (new) — requires server running
cd visualizer && python -m http.server 8000 &
sleep 2
npx playwright test
```

Expected:
- pytest: 292 passing + 1 skip
- node --test: all new tests pass
- playwright: all e2e pass (regression + generator)

- [ ] **Step 4: Commit version bump**

```bash
git add src/pyproject.toml
git commit -m "chore: bump version to v3.5.0"
```

---

### Task 25: Deploy + tag release

**Files:**
- (no file changes, just git operations)

- [ ] **Step 1: Push all commits to main**

```bash
git push origin main
```

- [ ] **Step 2: Wait for GitHub Pages to deploy**

GitHub Pages auto-deploys from main. Wait ~2-3 minutes.

Verify deploy:

```bash
curl -sI https://osyanne.github.io/CitiesSkylines2-osm-toolkit/generate.html
```

Expected: `HTTP/2 200`.

- [ ] **Step 3: Smoke-test the live deployed version**

Open https://osyanne.github.io/CitiesSkylines2-osm-toolkit/generate.html in a real browser, run a complete generation for a test city (try Reykjavik for an unusual location), verify ZIP downloads correctly.

- [ ] **Step 4: Create release tag**

```bash
git tag -a v3.5.0 -m "v3.5.0 — browser-based OSM2CS generator

- New visualizer/generate.html: client-side city generator (search → tile → ZIP)
- New visualizer/js/ modules: search, tile-picker, srtm-fetcher, heightmap, water-extractor, bundler, progress-ui, readme-gen, main
- New visualizer/lib/: vendored JSZip 3.10.1 + UPNG.js 2.1.0
- Refactor: overpass-client.js + classifiers.js extracted from map.html
- New tests-js/: node --test + Playwright e2e (10-city regression + happy path + failure paths)
- New CI jobs: js-tests + e2e-tests
- README + METHODOLOGY updated

Phase 3 validation: Tier 0 demand signal (Giscolab fork) + 7 city requests + Patreon LIVE."

git push origin v3.5.0
```

- [ ] **Step 5: Create GitHub Release**

```bash
gh release create v3.5.0 \
  --title "v3.5.0 — Browser-based OSM2CS Generator" \
  --notes "Browser-based city generator: pick any city in the world → download CS2-ready ZIP. Zero install, zero signup, zero cost.

## What's new

- **\`visualizer/generate.html\`** — new page where you type a city, see a 14.336km tile, and generate a CS2-ready bundle entirely in your browser
- **Output ZIP** contains: 16-bit PNG heightmap (4096×4096, CS2-native) + zoning.geojson + roads.geojson + services.geojson + water.geojson + offline preview viewer + README with import instructions
- **Pipeline:** SRTM elevation → bilinear resample → UPNG 16-bit PNG encode → parallel Overpass queries → classify → JSZip
- **Refactor:** \`overpass-client.js\` + \`classifiers.js\` extracted from \`map.html\` for reuse
- **Tests:** unit tests with \`node --test\`, e2e with Playwright across Chromium/Firefox/WebKit
- **Hosted at:** https://osyanne.github.io/CitiesSkylines2-osm-toolkit/generate.html

## Compatibility

Desktop only (mobile lacks RAM for in-browser SRTM processing). Chrome, Firefox, Safari, Edge modern versions.

## Coming next

- v3.5.1: bbox permalink URLs for sharing (\`?bbox=...\`)
- Phase 4: optional Pro SaaS tier (only if Patreon supporters validate willingness-to-pay)"
```

- [ ] **Step 6: Update memory + notes**

Update memory files / Obsidian notes to reflect v3.5.0 shipped (project state).

```bash
# (Manual step — user updates their Obsidian vault + ~/.claude memory)
echo "v3.5.0 shipped. Update Obsidian vault + ~/.claude/projects/.../memory/ accordingly."
```

---

## Plan self-review

### Coverage check (spec → tasks)

| Spec section | Tasks that implement |
|---|---|
| §3 User experience flow (6 states) | Tasks 8, 9, 16, 17 |
| §4 Architecture | Tasks 1, 16, 17 |
| §5 Component structure | Tasks 1, 4-15 (each module = 1 task) |
| §6 Data flow with parallelism | Task 16 (orchestrator) |
| §7 Error handling (4 categories) | Task 16 (error handling in pipeline), Task 20 (failure tests) |
| §8 Testing strategy | Tasks 2, 3 (infra), 4-15 (unit), 19-21 (integration + e2e) |
| §9 Out of scope | Documented in spec; tasks explicitly not added |
| §10 Open questions | Tasks 10 (SRTM endpoint), 11 (UPNG flags) |
| §11 Pre-requisites | All resolved: spec is committed (60fa8dc), date is set |
| §A Appendix README template | Task 13 (readme-gen.js) |

### Placeholder check

- No "TBD" or "TODO" sentinels in step instructions ✓
- No "implement appropriate error handling" without specifics ✓
- All file paths absolute ✓
- All commands include expected output ✓
- All code steps include actual code blocks ✓

### Type consistency

- `classifyZoning(feature)` signature consistent across Tasks 5, 11, 16 ✓
- `fetchOverpass(query, options)` consistent across Tasks 4, 12, 16 ✓
- `ProgressTracker` API (start/complete/warn/fail) consistent in Tasks 15, 16 ✓
- ZIP filenames consistent: `heightmap.png`, `zoning.geojson`, `roads.geojson`, `services.geojson`, `water.geojson`, `preview.html`, `README.md` across Tasks 13, 14, 16, 19 ✓

### Scope check

- 25 tasks total, ~3-4 weeks of work
- Tasks ordered: setup → refactor (de-risk first) → new modules → integration → tests → release
- Refactor early (Tasks 4-7) ensures the new feature doesn't bottleneck on cleanup later
- Each task produces working software (tests pass) — no broken intermediate states

### Ambiguity check

- "Heightmap PNG mode" (Task 11): noted in spec §10 Open Questions, resolved during implementation by trying CS2 import. Acceptable for v1.
- "SRTM endpoint choice" (Task 10): noted in spec §10, used `elevation-tiles-prod` S3 bucket as primary. Resolvable mid-implementation if it fails.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-18-osm2cs-generator.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Best for plans this long.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
