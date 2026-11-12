'use client';
import { useState } from 'react';
import { WordCloud } from './live-engagement';
import styles from './live-formats.module.css';

export type Pin = { x: number; y: number };
export function RankingInput({ options, value, onChange }: { options: string[]; value: string[]; onChange: (value: string[]) => void }) {
  const [dragged, setDragged] = useState<number | null>(null);
  const order = value.length ? value : options;
  function move(from: number, to: number) { if (to < 0 || to >= order.length) return; const copy = [...order]; const [item] = copy.splice(from, 1); copy.splice(to, 0, item); onChange(copy); }
  return <ol className={styles.ranking} aria-label="Reorder your ranking">{order.map((option, i) => <li key={option} draggable onDragStart={e => { setDragged(i); e.dataTransfer.effectAllowed = 'move'; }} onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (dragged !== null) move(dragged, i); setDragged(null); }} onDragEnd={() => setDragged(null)}>
    <span aria-hidden="true">⠿</span><b>{i + 1}</b><span>{option}</span><button type="button" className="secondary" aria-label={`Move ${option} up`} disabled={i === 0} onClick={() => move(i, i - 1)}>↑</button><button type="button" className="secondary" aria-label={`Move ${option} down`} disabled={i === order.length - 1} onClick={() => move(i, i + 1)}>↓</button>
  </li>)}</ol>;
}

export function LikertInput({ min, max, value, onChange }: { min: number; max: number; value: number | null; onChange: (value: number) => void }) {
  if (max - min > 20) return <label>Your rating<input type="number" min={min} max={max} step={1} value={value ?? ''} onChange={e => onChange(Number(e.target.value))} /></label>;
  return <fieldset className={styles.likert}><legend>Your rating</legend><div>{Array.from({ length: max - min + 1 }, (_, i) => min + i).map(n => <label key={n} className={value === n ? styles.selected : ''}><input type="radio" name="likert-rating" value={n} checked={value === n} onChange={() => onChange(n)} />{n}</label>)}</div><p><span>{min} · Low</span><span>{max} · High</span></p></fieldset>;
}

export function HotspotInput({ url, alt, value, onChange, target, pins = [] }: { url: string; alt: string; value: Pin | null; onChange?: (pin: Pin) => void; target?: Pin & { radius: number }; pins?: Pin[] }) {
  return <div><div className={styles.hotspot} onClick={e => { if (!onChange) return; const rect = e.currentTarget.getBoundingClientRect(); onChange({ x: Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)), y: Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height)) }); }}>
    {/* External image URLs are authored by the host; no server-side fetch. */}
    <img src={url} alt={alt || 'Tap the image to place your pin'} />
    {value && <span className={styles.pin} style={{ left: `${value.x * 100}%`, top: `${value.y * 100}%` }}>●</span>}
    {pins.map((pin, i) => <span key={i} className={styles.pin} style={{ left: `${pin.x * 100}%`, top: `${pin.y * 100}%`, opacity: .6 }}>●</span>)}
    {target && <svg className={styles.target} viewBox="0 0 1 1" preserveAspectRatio="none" aria-label="Correct target"><circle cx={target.x} cy={target.y} r={target.radius} fill="#25a67833" stroke="#127650" strokeWidth=".005" /></svg>}
  </div>{onChange && <><p>{value ? 'Pin placed. Tap again to move it.' : 'Tap the image to place your pin, or enter coordinates below.'}</p><div className={styles.coordinates}>{(['x', 'y'] as const).map(axis => <label key={axis}>{axis.toUpperCase()} (%)<input type="number" min={0} max={100} step={1} value={value ? Math.round(value[axis] * 100) : ''} onChange={e => onChange({ ...(value || { x: .5, y: .5 }), [axis]: Math.max(0, Math.min(1, Number(e.target.value) / 100)) })} /></label>)}</div></>}</div>;
}

export type DisplayQuestion = { title: string; kind: string; body?: string; options: string[]; minimum?: number; maximum?: number; image_url?: string; image_alt?: string; duration_seconds?: number };
export function LiveResults({ question, responses, target }: { question: DisplayQuestion; responses: { answer: unknown }[]; target?: Pin & { radius: number } }) {
  if (question.kind === 'word_cloud') return <WordCloud answers={responses.map(r => r.answer)} />;
  if (question.kind === 'hotspot') return <HotspotInput url={question.image_url || ''} alt={question.image_alt || ''} value={null} target={target} pins={responses.flatMap(r => r.answer && typeof r.answer === 'object' && 'x' in r.answer && 'y' in r.answer && typeof r.answer.x === 'number' && typeof r.answer.y === 'number' ? [{ x: r.answer.x, y: r.answer.y }] : [])} />;
  if (question.kind === 'ranking') {
    const ranked = question.options.map(option => { const positions = responses.flatMap(r => Array.isArray(r.answer) && r.answer.includes(option) ? [r.answer.indexOf(option) + 1] : []); return { option, average: positions.length ? positions.reduce((a, b) => a + b, 0) / positions.length : null }; }).sort((a, b) => (a.average ?? Infinity) - (b.average ?? Infinity));
    return <ol>{ranked.map(r => <li key={r.option}>{r.option} <small>{r.average === null ? 'No responses' : `Average rank ${r.average.toFixed(1)}`}</small></li>)}</ol>;
  }
  if (['scale', 'rating', 'nps'].includes(question.kind)) {
    const values = responses.flatMap(r => typeof r.answer === 'number' ? [r.answer] : []);
    const counts = new Map<number, number>(); values.forEach(v => counts.set(v, (counts.get(v) || 0) + 1));
    return <div><h2>{values.length ? `Average: ${(values.reduce((a, b) => a + b, 0) / values.length).toFixed(1)}` : 'Waiting for ratings'}</h2>{[...counts].sort((a, b) => a[0] - b[0]).map(([n, count]) => <div className="result-row" key={n}><span>{n}</span><progress max={values.length} value={count} /><strong>{count}</strong></div>)}</div>;
  }
  return <>{question.options.map(option => { const count = responses.filter(r => Array.isArray(r.answer) ? r.answer.includes(option) : r.answer === option).length; return <div className="result-row" key={option}><span>{option}</span><progress max={Math.max(1, responses.length)} value={count} /><strong>{count}</strong></div>; })}{!question.options.length && responses.map((r, i) => <p className="response-card" key={i}>{typeof r.answer === 'string' || typeof r.answer === 'number' ? r.answer : ''}</p>)}</>;
}
