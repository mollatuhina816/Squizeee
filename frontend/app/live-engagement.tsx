'use client';
import { authFetch } from './auth-fetch';
import { useCallback, useEffect, useRef, useState } from 'react';
import { readApiResponse } from './api-response';
import styles from './live-engagement.module.css';
import FullscreenCard from './fullscreen-card';

export type LiveEvent = { type: string; id: string; emoji?: string; nickname?: string; participant_id?: string };
export type RankedParticipant = { id: string; nickname: string; score: number; streak?: number; multiplier?: number; team?: number | null };
export function useEngagementEvents() {
  const [events, setEvents] = useState<(LiveEvent & { received: number; lane: number })[]>([]);
  const [winner, setWinner] = useState<LiveEvent | null>(null);
  const seen = useRef(new Set<string>());
  const onEvent = useCallback((event: LiveEvent) => {
    if (seen.current.has(event.id)) return;
    seen.current.add(event.id);
    if (seen.current.size > 500) seen.current.delete(seen.current.values().next().value!);
    if (event.type === 'reaction') setEvents(old => [...old.slice(-39), { ...event, received: Date.now(), lane: Math.random() * 80 + 5 }]);
    if (event.type === 'picker') setWinner(event);
  }, []);
  useEffect(() => { const timer = setInterval(() => setEvents(old => old.filter(e => Date.now() - e.received < 5000)), 1000); return () => clearInterval(timer); }, []);
  return { events, winner, onEvent };
}

export function ReactionOverlay({ events }: { events: (LiveEvent & { lane: number })[] }) {
  return <div className={styles.reactions} aria-hidden="true">{events.map(e => <span key={e.id} style={{ left: `${e.lane}%` }}>{e.emoji}</span>)}</div>;
}

export function ReactionBar({ sessionId, token, disabled }: { sessionId: string; token: string; disabled: boolean }) {
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function react(emoji: string) {
    setBusy(true);
    try { await readApiResponse(await fetch(`/api/v1/sessions/${sessionId}/reactions`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Participant-Token': token }, body: JSON.stringify({ emoji }) })); setError(''); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <div className={styles.reactionBar}><span>Send a reaction</span><div>{['❤️', '👏', '🔥', '😂'].map(emoji => <button key={emoji} aria-label={`Send ${emoji} reaction`} disabled={disabled || busy} onClick={() => react(emoji)}>{emoji}</button>)}</div>{error && <small role="alert">{error}</small>}</div>;
}

type AudienceEntry = { id: string; text: string; status: string; votes: number; voted: boolean; own: boolean };
export function AudiencePanel({ sessionId, token, host = false, displayOnly = false, signal, ended = false }: { sessionId: string; token?: string; host?: boolean; displayOnly?: boolean; signal?: string; ended?: boolean }) {
  const [questions, setQuestions] = useState<AudienceEntry[]>([]);
  const [text, setText] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const base = `/api/v1/sessions/${sessionId}`;
  const refresh = useCallback(async () => {
    try { const result = await readApiResponse<{ questions: AudienceEntry[] }>(await (host ? authFetch : fetch)(`${base}/${host ? 'host/audience' : 'audience'}`, { headers: token ? { 'X-Participant-Token': token } : {} })); setQuestions(result.questions); setError(''); }
    catch (e) { setError((e as Error).message); }
  }, [base, host, token]);
  useEffect(() => { void refresh(); }, [refresh, signal]);
  useEffect(() => { const t = setInterval(refresh, 10000); return () => clearInterval(t); }, [refresh]);
  async function mutate(path: string, body?: object) {
    setBusy(true); setError('');
    try { await readApiResponse(await (host ? authFetch : fetch)(base + path, { method: 'POST', headers: { 'Content-Type': 'application/json', ...(token ? { 'X-Participant-Token': token } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) })); if (path === '/audience') setText(''); await refresh(); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  const visible = displayOnly ? questions.filter(q => q.status === 'approved' || q.status === 'answered') : questions;
  return <FullscreenCard title="Audience Q&A" className={styles.audience}><p>{displayOnly ? 'The most popular audience questions rise to the top.' : host ? 'Approve incoming questions, then let the audience vote.' : 'Ask a question or upvote one you would like answered. New questions appear after host approval.'}</p>
    {!host && <form onSubmit={e => { e.preventDefault(); void mutate('/audience', { text }); }}><label>Your question<textarea value={text} maxLength={500} required onChange={e => setText(e.target.value)} disabled={ended || busy} /></label><button disabled={ended || busy || !text.trim()}>Submit question</button></form>}
    {error && <p role="alert" className="error">{error}</p>}
    {!visible.length && <p>No questions yet.</p>}
    <ul>{visible.map(q => <li key={q.id}><div><p>{q.text}</p><small>{q.status === 'pending' ? 'Awaiting approval' : q.status === 'answered' ? 'Answered' : q.status === 'hidden' ? 'Hidden' : `${q.votes} votes`}</small></div>
      {displayOnly ? null : host ? <div className={styles.moderation}>{q.status !== 'approved' && <button disabled={busy} onClick={() => mutate(`/audience/${q.id}/moderate`, { status: 'approved' })}>Approve</button>}{q.status === 'approved' && <button disabled={busy} onClick={() => mutate(`/audience/${q.id}/moderate`, { status: 'answered' })}>Mark answered</button>}{q.status !== 'hidden' && <button className="secondary" disabled={busy} onClick={() => mutate(`/audience/${q.id}/moderate`, { status: 'hidden' })}>Hide</button>}</div> : <button className="secondary" disabled={ended || busy || q.voted || q.own || q.status !== 'approved'} aria-label={`Upvote: ${q.text}`} onClick={() => mutate(`/audience/${q.id}/vote`)}>▲ {q.votes}{q.voted ? ' Voted' : ''}</button>}
    </li>)}</ul>
  </FullscreenCard>;
}

export function AnimatedRankings({ rows, highlightId }: { rows: RankedParticipant[]; highlightId?: string }) {
  const previous = useRef<Record<string, number>>({});
  const ranks = previous.current;
  useEffect(() => { previous.current = Object.fromEntries(rows.map((r, i) => [r.id, i])); }, [rows]);
  return <section className={styles.leaderboard} aria-label="Leaderboard">
    <div className={styles.rankingSummary}><span>{rows.length} participant{rows.length === 1 ? '' : 's'}</span><span>Scores in points</span></div>
    <div className={styles.rankingHeader} aria-hidden="true"><span>Rank</span><span>Participant</span><span>Change</span><span>Points</span></div>
    <div className={styles.rankings} role="list" aria-label="Live rankings">{rows.map((r, i) => {
      const delta = ranks[r.id] === undefined ? 0 : ranks[r.id] - i;
      const isYou = r.id === highlightId;
      const initials = r.nickname.trim().split(/\s+/).slice(0, 2).map(part => part[0]).join('').toUpperCase();
      return <div role="listitem" key={r.id} className={`${styles.rank} ${isYou ? styles.you : ''}`}>
        <strong className={`${styles.rankNumber} ${i < 3 ? styles.topRank : ''}`}>{String(i + 1).padStart(2, '0')}</strong>
        <div className={styles.rankingPerson}><span className={styles.rankingAvatar} aria-hidden="true">{initials || '?'}</span><div className={styles.rankingIdentity}><span className={styles.rankingName} title={r.nickname}>{r.nickname}</span><div className={styles.rankingBadges}>{isYou && <span className={styles.youBadge}>You</span>}{r.streak && r.streak >= 3 ? <span className={styles.streakBadge}>{r.streak} streak{(r.multiplier || 1) > 1 ? ` / ${r.multiplier}x` : ''}</span> : null}</div></div></div>
        <small className={styles.rankingChange} aria-label={delta > 0 ? `Up ${delta} places` : delta < 0 ? `Down ${-delta} places` : 'Rank unchanged'}>{delta > 0 ? `+${delta}` : delta < 0 ? `-${-delta}` : '-'}</small>
        <b className={styles.rankingScore}>{(r.score / 1000).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</b>
      </div>;
    })}</div>
    {!rows.length && <p className={styles.rankingEmpty}>Rankings will appear when participants join.</p>}
  </section>;
}

export function WordCloud({ answers }: { answers: unknown[] }) {
  const counts = new Map<string, number>();
  answers.forEach(a => { if (typeof a !== 'string') return; for (const word of a.normalize('NFKC').toLocaleLowerCase().match(/[\p{L}\p{N}]+/gu) || []) counts.set(word, (counts.get(word) || 0) + 1); });
  const words = [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 80);
  const max = Math.max(1, ...words.map(w => w[1]));
  return <div className={styles.cloud} aria-label="Live word cloud">{words.length ? words.map(([word, count], i) => <span key={word} style={{ fontSize: `${18 + 48 * Math.sqrt(count / max)}px`, color: ['#7750ad', '#118c84', '#da537d', '#4279bf'][i % 4] }} title={`${count} mentions`}>{word}<span className={styles.srOnly}> ({count} mentions)</span></span>) : <p>Words will grow here as answers arrive.</p>}</div>;
}

export function RandomPicker({ sessionId, rows, winner, onEvent }: { sessionId: string; rows: RankedParticipant[]; winner: LiveEvent | null; onEvent: (e: LiveEvent) => void }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const [rotation, setRotation] = useState(0); const [visible, setVisible] = useState(false);
  useEffect(() => { if (!winner) return; setVisible(false); setRotation(old => old + 1440 + (360 - (rows.findIndex(r => r.id === winner.participant_id) / Math.max(1, rows.length)) * 360)); const t = setTimeout(() => setVisible(true), 3200); return () => clearTimeout(t); }, [winner]); // Names can update without restarting a spin.
  async function spin() { setBusy(true); setError(''); try { onEvent(await readApiResponse<LiveEvent>(await authFetch(`/api/v1/sessions/${sessionId}/picker`, { method: 'POST' }))); } catch (e) { setError((e as Error).message); } finally { setTimeout(() => setBusy(false), 3300); } }
  return <FullscreenCard title="Random spotlight" className={styles.picker}><div className={styles.wheelWrap}><span className={styles.pointer}>▼</span><div className={styles.wheel} style={{ transform: `rotate(${rotation}deg)` }}>✦</div></div><button disabled={busy || !rows.length} onClick={spin}>{busy ? 'Spinning…' : 'Pick a participant'}</button>{visible && winner && <p role="status">🎉 {winner.nickname}</p>}{error && <p role="alert" className="error">{error}</p>}</FullscreenCard>;
}
