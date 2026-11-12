'use client';
import { useEffect, useRef, useState } from 'react';

type Row = { id: string; nickname: string; score: number };

/**
 * Animated vertical bar chart of participant scores.
 * Bars keep a stable slot per participant (by join order) so heights visibly
 * rise and fall as answers arrive; a brief up/down flash marks score changes.
 */
export default function LeaderboardChart({ rows, highlightId, title }: { rows: Row[]; highlightId?: string; title?: string }) {
  const order = useRef<string[]>([]);
  const prev = useRef<Record<string, number>>({});
  const [delta, setDelta] = useState<Record<string, 'up' | 'down'>>({});

  rows.forEach(r => { if (!order.current.includes(r.id)) order.current.push(r.id); });
  order.current = order.current.filter(id => rows.some(r => r.id === id));

  useEffect(() => {
    const changed: Record<string, 'up' | 'down'> = {};
    rows.forEach(r => {
      const before = prev.current[r.id];
      if (before !== undefined && before !== r.score) changed[r.id] = r.score > before ? 'up' : 'down';
      prev.current[r.id] = r.score;
    });
    if (!Object.keys(changed).length) return;
    setDelta(changed);
    const t = setTimeout(() => setDelta({}), 1200);
    return () => clearTimeout(t);
  }, [rows]);

  const ranks = new Map(rows.map((r, i) => [r.id, i + 1]));
  const byId = new Map(rows.map(r => [r.id, r]));
  const max = Math.max(1, ...rows.map(r => r.score));
  const slots = order.current.map(id => byId.get(id)!).filter(Boolean);
  const box = useRef<HTMLElement>(null);
  const [full, setFull] = useState(false);
  useEffect(() => {
    const onChange = () => setFull(document.fullscreenElement === box.current);
    document.addEventListener('fullscreenchange', onChange);
    return () => document.removeEventListener('fullscreenchange', onChange);
  }, []);
  const toggle = () => { if (document.fullscreenElement) void document.exitFullscreen(); else void box.current?.requestFullscreen(); };

  return (
    <figure ref={box} className={`lb-chart ${full ? 'lb-full' : ''}`} aria-label={title || 'Leaderboard bar chart'}>
      <button type="button" className="lb-fs-btn" onClick={toggle} aria-label={full ? 'Exit full screen' : 'Full screen'} title={full ? 'Exit full screen (Esc)' : 'Full screen'}>
        {full
          ? <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 3v6H3M15 3v6h6M9 21v-6H3M15 21v-6h6"/></svg>
          : <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 9V3h6M21 9V3h-6M3 15v6h6M21 15v6h-6"/></svg>}
        <span>{full ? 'Exit' : 'Full screen'}</span>
      </button>
      {full && title && <h2 className="lb-full-title">{title}</h2>}
      <div className="lb-chart-plot" style={{ minWidth: `${Math.max(slots.length * 64, 240)}px` }}>
        {slots.map(r => {
          const rank = ranks.get(r.id)!;
          const pct = Math.max(2, (r.score / max) * 100);
          return (
            <div key={r.id} className={`lb-col ${r.id === highlightId ? 'lb-you' : ''} ${rank <= 3 ? `lb-rank-${rank}` : ''} ${delta[r.id] ? `lb-${delta[r.id]}` : ''}`}>
              <span className="lb-value">{(r.score / 1000).toFixed(1)}{delta[r.id] === 'up' ? ' ▲' : delta[r.id] === 'down' ? ' ▼' : ''}</span>
              <div className="lb-track"><div className="lb-bar" style={{ height: `${pct}%` }} title={`${r.nickname}: ${(r.score / 1000).toFixed(3)} points`} /></div>
              <span className="lb-rank">#{rank}</span>
              <span className="lb-name" title={r.nickname}>{r.nickname}{r.id === highlightId ? ' (you)' : ''}</span>
            </div>
          );
        })}
      </div>
    </figure>
  );
}
