import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import ts from 'typescript';

const source = readFileSync(new URL('../app/auth-routing.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const { getPostAuthPath } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);

test('students are sent to their own dashboard after sign-in', () => {
  assert.equal(getPostAuthPath({ profession: 'student', is_super_admin: false }), '/student');
});

test('admins stay in the workspace admin area', () => {
  assert.equal(getPostAuthPath({ profession: 'teacher', is_super_admin: true }), '/admin');
});

test('teachers without admin access remain in the workspace root', () => {
  assert.equal(getPostAuthPath({ profession: 'teacher', is_super_admin: false }), '/');
});
