import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import vm from 'node:vm';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';

const require = createRequire(import.meta.url);
const app = fileURLToPath(new URL('../app/', import.meta.url));
function loader(overrides = {}, globals = {}) {
  const cache = new Map();
  function load(filename) {
    if (cache.has(filename)) return cache.get(filename).exports;
    const text = readFileSync(filename, 'utf8');
    const module = { exports: {} }; cache.set(filename, module);
    const source = ts.transpileModule(text, { compilerOptions: { target: ts.ScriptTarget.ES2017, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
    const localRequire = name => {
      if (Object.hasOwn(overrides, name)) return overrides[name];
      if (name.endsWith('.module.css')) return { __esModule: true, default: new Proxy({}, { get: (_, key) => String(key) }) };
      if (!name.startsWith('.')) return require(name);
      const base = path.resolve(path.dirname(filename), name);
      try { return load(`${base}.ts`); } catch (error) { if (error.code !== 'ENOENT') throw error; }
      return load(`${base}.tsx`);
    };
    vm.runInNewContext(source, { module, exports: module.exports, require: localRequire, ...globals }, { filename });
    return module.exports;
  }
  return name => load(path.join(app, name));
}

const load = loader();
const { countdownSeconds } = load('countdown.ts');
const WaitingRoom = load('student-quiz-waiting-room.tsx').default;
const { ReconnectingIndicator, ProcessingIndicator } = load('ui-primitives.tsx');

test('countdown follows server timestamps and elapsed time rather than interval ticks', () => {
  assert.equal(countdownSeconds('2026-10-11T10:00:05Z', '2026-10-11T10:00:00Z', 30, 15000), 10);
  assert.equal(countdownSeconds('2026-10-11T10:00:05Z', '2026-10-11T10:00:00Z', 30, 60000), 0);
});
test('countdown handles unavailable dates and bounds clock skew', () => {
  assert.equal(countdownSeconds('invalid', 'invalid', 30, 0), 0);
  assert.equal(countdownSeconds('2026-10-11T10:00:00Z', null, 30, 0), 0);
  assert.equal(countdownSeconds('2026-10-11T10:00:00Z', '2026-10-11T10:00:05Z', 30, 0), 30);
});
test('waiting room renders supplied identity/count without exposing credentials', () => {
  const html = renderToStaticMarkup(React.createElement(WaitingRoom, { connection: 'Live', nickname: 'Learner <one>', participantCount: 0, code: '123456' }));
  assert.match(html, /You&#x27;re In!/);
  assert.match(html, /Learner &lt;one&gt;/);
  assert.match(html, /0 participants/);
  assert.match(html, /123456/);
  assert.match(html, /Live connection/);
  assert.doesNotMatch(html, /role="timer"|token|Waiting countdown/);
});
test('waiting room omits unavailable session metadata', () => {
  const html = renderToStaticMarkup(React.createElement(WaitingRoom, { connection: 'Reconnecting' }));
  assert.doesNotMatch(html, /Playing as|In the room|Session code|waiting-quiz-title/);
  assert.match(html, /Reconnecting/);
  assert.match(html, /Waiting for your teacher/);
});
test('connection indicator cannot claim live connectivity while reconnecting', () => {
  const html = renderToStaticMarkup(React.createElement(ReconnectingIndicator, { connection: 'Reconnecting' }));
  assert.match(html, /role="status"/);
  assert.doesNotMatch(html, /Live connection|is-connected/);
});
test('processing uses indeterminate status without fabricated percentage', () => {
  const html = renderToStaticMarkup(React.createElement(ProcessingIndicator, null, 'Processing document'));
  assert.match(html, /role="status"/);
  assert.doesNotMatch(html, /aria-valuenow|\d+%|complete/i);
});

function eventTarget(extra = {}) {
  const handlers = new Map();
  return { ...extra, handlers, addEventListener(name, callback) { handlers.set(name, callback); }, removeEventListener(name) { handlers.delete(name); }, fire(name) { handlers.get(name)?.(); } };
}
test('waiting messages stop when hidden or reduced motion is enabled and clean up', () => {
  const document = eventTarget({ hidden: false });
  const media = eventTarget({ matches: false });
  const timers = new Map(); const cleanups = []; let nextId = 0;
  const react = { ...React, useId: () => 'waiting-test', useState: initial => [initial, () => {}], useEffect: effect => cleanups.push(effect()) };
  const customLoad = loader({ react }, { document, window: { matchMedia: () => media }, setInterval: callback => { timers.set(++nextId, callback); return nextId; }, clearInterval: id => timers.delete(id) });
  customLoad('student-quiz-waiting-room.tsx').default({ connection: 'Live' });
  assert.equal(timers.size, 1);
  document.hidden = true; document.fire('visibilitychange'); assert.equal(timers.size, 0);
  document.hidden = false; document.fire('visibilitychange'); assert.equal(timers.size, 1);
  media.matches = true; media.fire('change'); assert.equal(timers.size, 0);
  cleanups.forEach(cleanup => cleanup?.());
  assert.equal(document.handlers.size, 0); assert.equal(media.handlers.size, 0);
});
test('quiz display resynchronizes after tab suspension and removes its listeners', () => {
  const document = eventTarget(); const cleanups = []; const timers = new Map(); let now = 1000; let remaining;
  const react = { ...React, useState: initial => [initial, value => { remaining = value; }], useEffect: effect => cleanups.push(effect()) };
  const customLoad = loader({ react }, { document, performance: { now: () => now }, setInterval: callback => { timers.set(1, callback); return 1; }, clearInterval: id => timers.delete(id) });
  customLoad('use-quiz-countdown.ts').useQuizCountdown('2026-10-11T10:00:05Z', '2026-10-11T10:00:00Z', 30);
  assert.equal(remaining, 25);
  now += 20000; document.fire('visibilitychange'); assert.equal(remaining, 5);
  now += 10000; document.fire('visibilitychange'); assert.equal(remaining, 0);
  cleanups.forEach(cleanup => cleanup?.());
  assert.equal(document.handlers.size, 0); assert.equal(timers.size, 0);
});

test('paused countdown stays frozen as client time passes', () => {
  const document = eventTarget(); let now = 0; let remaining; let tick;
  const react = { ...React, useState: initial => [initial, value => { remaining = value; }], useEffect: effect => effect() };
  const customLoad = loader({ react }, { document, performance: { now: () => now }, setInterval: callback => { tick = callback; return 1; }, clearInterval: () => {} });
  customLoad('use-quiz-countdown.ts').useQuizCountdown('2026-10-11T10:00:25Z', '2026-10-11T10:00:00Z', 30, '2026-10-11T10:00:05Z');
  assert.equal(remaining, 25);
  now += 60000; tick(); assert.equal(remaining, 25);
});

test('word cloud merges case and scales repeated words without rendering markup', () => {
  const WordCloud = load('live-engagement.tsx').WordCloud;
  const html = renderToStaticMarkup(React.createElement(WordCloud, { answers: ['Learn learn', 'LEARN explore', '<script>alert(1)</script>'] }));
  assert.match(html, /3 mentions/);
  assert.match(html, /explore/);
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /font-size:66px/);
});

test('participant page replaces waiting artwork with the real question or ended state', () => {
  const credentials = { session_id: 'session-one', participant_id: 'participant-one', token: 'private-token', code: '123456' };
  const snapshot = { state: 'waiting', revision: 1, active_index: 0, score: 0, completed: false, participant_count: 1, leaderboard: [{ id: 'participant-one', nickname: 'Test learner', score: 0 }], question: null };
  function render(state) {
    const states = ['', false, credentials, state, '', false, '', '123456']; let index = 0;
    const react = { ...React, useRef: initial => ({ current: initial }), useState: initial => [index < states.length ? states[index++] : initial, () => {}], useEffect: () => {}, useCallback: callback => callback };
    const customLoad = loader({ react, '../use-live-socket': { useLiveSocket: () => 'Live' }, '../use-quiz-countdown': { useQuizCountdown: () => 25 } });
    return renderToStaticMarkup(React.createElement(customLoad('join/page.tsx').default));
  }
  const waiting = render(snapshot); assert.match(waiting, /student-waiting-room/); assert.doesNotMatch(waiting, /private-token/);
  const open = render({ ...snapshot, state: 'open', question: { kind: 'mcq', title: 'Real question', body: '', options: ['One', 'Two'], duration_seconds: 30 } });
  assert.doesNotMatch(open, /student-waiting-room/); assert.match(open, /Real question/); assert.match(open, /Submit answer/); assert.doesNotMatch(open, /Mark for Review|Save &amp; Next|private-token/);
  const ended = render({ ...snapshot, state: 'ended' }); assert.doesNotMatch(ended, /student-waiting-room|Submit answer/); assert.match(ended, /Preview answers/);
});

test('join entry screen asks only for email first and shows mandatory registration fields for new students', () => {
  function renderEntry(isRegistering) {
    const states = ['', isRegistering, null, null, '', false, '', '478062', 'new@example.com']; let index = 0;
    const react = { ...React, useRef: initial => ({ current: initial }), useState: initial => [index < states.length ? states[index++] : initial, () => {}], useEffect: () => {}, useCallback: callback => callback };
    const customLoad = loader({ react, '../use-live-socket': { useLiveSocket: () => 'Live' }, '../use-quiz-countdown': { useQuizCountdown: () => 25 } });
    return renderToStaticMarkup(React.createElement(customLoad('join/page.tsx').default));
  }
  const stepOne = renderEntry(false);
  assert.doesNotMatch(stepOne, /Join with name|Use email profile|placeholder="6-digit code or Quiz ID"/);
  assert.match(stepOne, /Email Address/);
  assert.match(stepOne, /type="hidden" name="quiz_id" value="478062"/);
  assert.doesNotMatch(stepOne, /Institute Name|Phone Number/);

  const stepTwo = renderEntry(true);
  assert.match(stepTwo, /Complete Your Profile/);
  assert.match(stepTwo, /Full Name/);
  assert.match(stepTwo, /Institute Name/);
  assert.match(stepTwo, /Stream/);
  assert.match(stepTwo, /Semester/);
  assert.match(stepTwo, /Phone Number/);
});

test('bank filters and preview keep real data and omit answer keys', () => {
  const items = [
    { id: 'one', question: { title: 'Cell structures', kind: 'mcq', body: 'A supporting paragraph', options: ['Nucleus', 'Wall'], correct_answers: ['Nucleus'] }, subject: 'Biology', chapter: 'Cells', topic: 'Structure', difficulty: 'easy' },
    { id: 'two', question: { title: 'Solar energy', kind: 'poll', options: ['Yes', 'No'] }, subject: 'Science', chapter: '', topic: '', difficulty: 'medium' },
  ];
  const states = [items, '', 'Cells', 'mcq', false]; let index = 0;
  const react = { ...React, useState: initial => [index < states.length ? states[index++] : initial, () => {}], useEffect: () => {}, useCallback: callback => callback };
  const customLoad = loader({ react, 'next/navigation': { useParams: () => ({ org: 'org-one' }) } });
  const html = renderToStaticMarkup(React.createElement(customLoad('bank/[org]/page.tsx').default));
  assert.match(html, /Cell structures/); assert.match(html, /A supporting paragraph/); assert.match(html, /1 shown/);
  assert.doesNotMatch(html.match(/<div class="bank-grid">[\s\S]*$/)[0], /Solar energy|correct_answers|Correct answer:/);
});

test('question bank picker filters by question type and keeps search input', () => {
  const items = [
    { id: 'one', question: { title: 'Mitosis phases', kind: 'mcq', options: ['A', 'B'] }, subject: 'Biology', topic: 'Cells', difficulty: 'easy' },
    { id: 'two', question: { title: 'Earth is round', kind: 'true_false', options: ['True', 'False'] }, subject: 'Science', topic: 'Space', difficulty: 'easy' },
  ];
  const states = [true, items, new Set(), '', 'true_false', false, '']; let index = 0;
  const react = { ...React, useState: initial => [index < states.length ? states[index++] : initial, () => {}], useEffect: () => {}, useRef: () => ({ current: null }) };
  const customLoad = loader({ react, './use-dialog-focus': { useDialogFocus: () => ({ current: null }) } });
  const html = renderToStaticMarkup(React.createElement(customLoad('question-bank-picker.tsx').default, { org: 'org-one', onAdd: () => {} }));
  assert.match(html, /Earth is round/);
  assert.doesNotMatch(html, /Mitosis phases/);
  assert.match(html, /True \/ False/);
  assert.match(html, /Question, subject, or topic/);
});

test('selecting and submitting a live answer preserves the existing API and participant identity', async () => {
  const credentials = { session_id: 'session-one', participant_id: 'participant-one', token: 'private-token', code: '123456' };
  const question = { kind: 'mcq', title: 'A question', body: '', options: ['One', 'Two'], duration_seconds: 30 };
  const snapshot = { state: 'open', revision: 2, active_index: 0, score: 0, leaderboard: [], question };
  const states = ['', false, credentials, snapshot, '', false, '', '123456']; let index = 0;
  const requests = [];
  const react = { ...React, useRef: initial => ({ current: initial }), useState: initial => {
    const slot = index++;
    if (slot >= states.length) states[slot] = initial;
    return [states[slot], value => { states[slot] = typeof value === 'function' ? value(states[slot]) : value; }];
  }, useEffect: () => {}, useCallback: callback => callback };
  const customLoad = loader({ react, '../use-live-socket': { useLiveSocket: () => 'Live' }, '../use-quiz-countdown': { useQuizCountdown: () => 25 } }, {
    fetch: async (url, options) => { requests.push({ url, options }); return new Response(JSON.stringify({ accepted: true, snapshot: { ...snapshot, active_index: 1 } }), { headers: { 'Content-Type': 'application/json' } }); },
  });
  const Page = customLoad('join/page.tsx').default;
  const render = () => { index = 0; return Page(); };
  function find(element, predicate) {
    if (!React.isValidElement(element)) return null;
    if (predicate(element)) return element;
    for (const child of React.Children.toArray(element.props.children)) { const match = find(child, predicate); if (match) return match; }
    return null;
  }
  find(render(), element => element.type === 'input' && element.props.name === 'answer').props.onChange();
  await find(render(), element => element.type === 'button' && element.props.children === 'Submit answer').props.onClick();
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, '/api/v1/sessions/session-one/responses');
  assert.equal(requests[0].options.headers['X-Participant-Token'], credentials.token);
  assert.deepEqual(JSON.parse(requests[0].options.body), { question_index: 0, answer: 'One' });
  assert.equal(states[2], credentials); assert.equal(states[3].active_index, 1); assert.equal(states[5], false);
});

test('dialog traps forward/backward keyboard focus and restores its trigger and scroll', () => {
  const trigger = { isConnected: true, focus() { document.activeElement = trigger; } };
  const first = { getClientRects: () => [1], focus() { document.activeElement = first; } };
  const last = { getClientRects: () => [1], focus() { document.activeElement = last; } };
  const dialog = eventTarget({ focus() { document.activeElement = dialog; }, querySelectorAll: () => [first, last], contains: element => [first, last, dialog].includes(element) });
  const document = { activeElement: trigger, body: { style: { overflow: 'auto' } } };
  const cleanups = [];
  const react = { ...React, useRef: () => ({ current: dialog }), useEffect: effect => cleanups.push(effect()) };
  const customLoad = loader({ react }, { document, HTMLElement: Object });
  customLoad('use-dialog-focus.ts').useDialogFocus(true);
  assert.equal(document.activeElement, dialog); assert.equal(document.body.style.overflow, 'hidden');
  let prevented = false;
  dialog.handlers.get('keydown')({ key: 'Tab', shiftKey: false, preventDefault() { prevented = true; } });
  assert.equal(document.activeElement, first); assert.equal(prevented, true);
  dialog.handlers.get('keydown')({ key: 'Tab', shiftKey: true, preventDefault() {} }); assert.equal(document.activeElement, last);
  cleanups.forEach(cleanup => cleanup?.());
  assert.equal(document.activeElement, trigger); assert.equal(document.body.style.overflow, 'auto'); assert.equal(dialog.handlers.size, 0);
});
