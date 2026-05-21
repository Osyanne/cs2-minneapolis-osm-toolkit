// Mock fetch implementation for unit tests.
// Returns the FIRST response whose .url regex matches.
// Order matters: more specific patterns must come first.
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
      blob: async () => {
        const b = match.body;
        if (b instanceof Blob) return b;
        if (b instanceof ArrayBuffer || ArrayBuffer.isView(b)) return new Blob([b]);
        if (typeof b === 'string') return new Blob([b]);
        return new Blob([JSON.stringify(b)], { type: 'application/json' });
      },
      arrayBuffer: async () => {
        const b = match.body;
        if (b instanceof ArrayBuffer) return b;
        if (ArrayBuffer.isView(b)) return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);
        if (typeof b === 'string') return new TextEncoder().encode(b).buffer;
        return new TextEncoder().encode(JSON.stringify(b)).buffer;
      }
    };
  };
  fn.calls = calls;
  return fn;
}
