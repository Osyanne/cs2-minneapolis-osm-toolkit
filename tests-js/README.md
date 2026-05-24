# JS Tests

Node.js native test runner (`node --test`), zero deps.

> **Requires Node ≥20** for the built-in `node --test` runner.

## Running

From repo root:

```bash
node --test "tests-js/**/*.test.js"
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
└── *.test.js          Unit tests for each visualizer/js/ module
```

Playwright e2e tests will live in `tests-js/e2e/` (added by Task 6).

## Conventions

- File naming: `<module>.test.js` (matches module being tested)
- Use `node --test`'s `test()` + `assert` from `node:assert`
- Import the module under test via relative path: `../visualizer/js/<module>.js`
- Mock external fetches via `helpers/mock-fetch.js`
- Tests should run in <100ms each (no real network calls)
