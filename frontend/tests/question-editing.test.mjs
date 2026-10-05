import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
const source = readFileSync(new URL('../app/question-editing.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } }).outputText;
const { renamedAnswers, cleanQuestion } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`);
test('renaming default options updates the selected answer', () => {
  assert.deepEqual(renamedAnswers(['Option A','Option B'], ['Option A'], ['Paris','London']), ['Paris']);
});
test('reordering options preserves the selected answer', () => {
  assert.deepEqual(renamedAnswers(['Paris','London'], ['Paris'], ['London','Paris']), ['Paris']);
});
test('deleted answers are removed', () => {
  assert.deepEqual(renamedAnswers(['A','B','C'], ['C'], ['A','B']), []);
});
test('blank lines and surrounding whitespace are removed before saving', () => {
  assert.deepEqual(cleanQuestion({options:[' Paris ','London',''],correct_answers:[' Paris ','']}),
    {options:['Paris','London'],correct_answers:['Paris']});
});
