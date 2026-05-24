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
