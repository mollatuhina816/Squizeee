import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

const source = ts.transpileModule(readFileSync(new URL('../app/auth-fetch.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;

function client(fetch) {
  const exports = {};
  vm.runInNewContext(source, { exports, fetch, URL, Request });
  return exports.authFetch;
}
const response = status => new Response('{}', { status });

test('expired access renews once and preserves the Present request on retry', async () => {
  let renewed = false;
  const calls = [];
  const fetch = client(async (url, init) => {
    calls.push([url, init]);
    if (url.endsWith('/auth/me')) return response(401);
    if (url.endsWith('/auth/refresh')) { renewed = true; return response(200); }
    return response(renewed ? 201 : 401);
  });
  const init = { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"team_mode":true}' };
  assert.equal((await fetch('/api/v1/organizations/org/presentations/id/sessions', init)).status, 201);
  assert.equal(calls.length, 4);
  assert.equal(calls[0][1], init);
  assert.equal(calls[3][1], init);
});

test('parallel unauthorized requests share one rotation', async () => {
  let renewals = 0;
  let renewed = false;
  const fetch = client(async url => {
    if (url.endsWith('/auth/me')) return response(401);
    if (url.endsWith('/auth/refresh')) { renewals++; renewed = true; return response(200); }
    return response(renewed ? 200 : 401);
  });
  const results = await Promise.all([fetch('/slides'), fetch('/host'), fetch('/ticket')]);
  assert.ok(results.every(result => result.status === 200));
  assert.equal(renewals, 1);
});

test('a session renewed by another tab does not rotate again', async () => {
  const calls = [];
  const fetch = client(async url => {
    calls.push(url);
    return response(url.endsWith('/auth/me') || calls.length > 2 ? 200 : 401);
  });
  assert.equal((await fetch('/slides')).status, 200);
  assert.deepEqual(calls, ['/slides', '/api/v1/auth/me', '/slides']);
});

test('expired refresh returns the original failure without a retry loop', async () => {
  const calls = [];
  const fetch = client(async url => { calls.push(url); return response(401); });
  assert.equal((await fetch('/slides')).status, 401);
  assert.equal(calls.length, 3);
});

test('login failures, forbidden actions and successful calls do not refresh', async () => {
  const calls = [];
  const fetch = client(async url => { calls.push(url); return response(url === '/forbidden' ? 403 : url === '/ok' ? 200 : 401); });
  for (const url of ['/api/v1/auth/login', '/api/v1/auth/register', '/api/v1/auth/logout', '/api/v1/auth/refresh', '/forbidden', '/ok']) {
    await fetch(url);
  }
  assert.equal(calls.length, 6);
});

test('a retry that still fails is returned without another refresh', async () => {
  const calls = [];
  const fetch = client(async url => { calls.push(url); return response(url.endsWith('/auth/me') ? 200 : 401); });
  assert.equal((await fetch('/slides')).status, 401);
  assert.equal(calls.length, 3);
});
