'use client';
import { useEffect, useRef, useState } from 'react';

type Row = { id: string; nickname: string; score: number };

const COLORS = ['#7c6cff', '#22d3ee', '#f472b6', '#fbbf24', '#34d399', '#fb7185', '#60a5fa', '#a78bfa', '#f97316', '#2dd4bf'];
const MAX_SLICES = 8;
const R = 70;
const C = 2 * Math.PI * R;

/**
 * Live pie chart of students' share of total points.
 * Slices keep a stable colour per student and animate (stroke-dasharray transition)
 * so they visibly grow or shrink as answers are scored.
 */
export default function LivePieChart({ rows }: { rows: Row[] }) {
  const colorOf = useRef<Record<string, string>>({});
  const prev = useRef<Record<string, number>>({});
  const [delta, setDelta] = useState<Record<string, 'up' | 'down'>>({});

  rows.forEach(r => { if (!colorOf.current[r.id]) colorOf.current[r.id] = COLORS[Object.keys(colorOf.current).length % COLORS.length]; });

  const total = rows.reduce((s, r) => s + Math.max(0, r.score), 0);
  const pctOf = (score: number) => (total ? (Math.max(0, score) / total) * 100 : 0);

  useEffect(() => {
    const changed: Record<string, 'up' | 'down'> = {};
    rows.forEach(r => {
      const before = prev.current[r.id];
      const now = pctOf(r.score);
      if (before !== undefined && Math.abs(before - now) > 0.05) changed[r.id] = now > before ? 'up' : 'down';
      prev.current[r.id] = now;
    });
    if (!Object.keys(changed).length) return;
    setDelta(changed);
    const t = setTimeout(() => setDelta({}), 1500);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows]);

  const sorted = [...rows].sort((a, b) => b.score - a.score);
  const top = sorted.slice(0, MAX_SLICES);
  const restScore = sorted.slice(MAX_SLICES).reduce((s, r) => s + Math.max(0, r.score), 0);
  const slices = [...top.map(r => ({ id: r.id, label: r.nickname, score: r.score, color: colorOf.current[r.id] })),
    ...(restScore > 0 ? [{ id: '__rest', label: `Others (${sorted.length - MAX_SLICES})`, score: restScore, color: '#94a3b8' }] : [])];

  let offset = 0;
  return (
    <div className="pie-live">
      <div className="pie-live-chart">
        <svg viewBox="0 0 200 200" role="img" aria-label="Pie chart of each student's share of points">
          <circle cx="100" cy="100" r={R} fill="none" stroke="rgba(120,120,160,.15)" strokeWidth="44" />
          {total > 0 && slices.map(s => {
            const len = (pctOf(s.score) / 100) * C;
            const el = (
              <circle key={s.id} className={`pie-slice ${delta[s.id] ? `pie-${delta[s.id]}` : ''}`} cx="100" cy="100" r={R} fill="none"
                stroke={s.color} strokeWidth="44" strokeDasharray={`${len} ${C - len}`} strokeDashoffset={-offset}
                transform="rotate(-90 100 100)"><title>{`${s.label}: ${pctOf(s.score).toFixed(1)}%`}</title></circle>
            );
            offset += len;
            return el;
          })}
        </svg>
        <div className="pie-live-center"><strong>{(total / 1000).toFixed(1)}</strong><span>total points</span></div>
      </div>
      {total > 0 ? (
        <ul className="pie-live-legend">
          {slices.map(s => (
            <li key={s.id} className={delta[s.id] ? `pie-${delta[s.id]}` : ''}>
              <i style={{ background: s.color }} />
              <span title={s.label}>{s.label}</span>
              <b>{pctOf(s.score).toFixed(1)}%{delta[s.id] === 'up' ? ' ▲' : delta[s.id] === 'down' ? ' ▼' : ''}</b>
            </li>
          ))}
        </ul>
      ) : <p className="pie-live-empty">The chart comes alive as students start answering.</p>}
    </div>
  );
}
