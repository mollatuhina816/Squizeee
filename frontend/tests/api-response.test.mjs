import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

const source = readFileSync(new URL('../app/api-response.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const { readApiResponse } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);

test('plain-text proxy failure becomes a useful error', async () => {
  await assert.rejects(readApiResponse(new Response('Internal Server Error', { status: 500 })),
    /Unable to reach the application service/);
});

test('JSON authentication errors retain the server message', async () => {
  await assert.rejects(readApiResponse(Response.json({ detail: 'Invalid email or password' }, { status: 401 })),
    /Invalid email or password/);
});

test('validation errors do not display raw JSON', async () => {
  await assert.rejects(readApiResponse(Response.json({ detail: [{ msg: 'invalid' }] }, { status: 422 })),
    /invalid/);
});

test('successful JSON is returned', async () => {
  assert.deepEqual(await readApiResponse(Response.json({ id: 'owner' })), { id: 'owner' });
});

test('invalid successful responses are reported clearly', async () => {
  await assert.rejects(readApiResponse(new Response('<html>unexpected</html>')), /invalid response/);
});
