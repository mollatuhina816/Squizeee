'use client';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import FullscreenCard from '../../fullscreen-card';
import { useEffect, useState } from 'react';
import { AnimatedEmptyState, LoadingSkeleton } from '../../ui-primitives';
import { readApiResponse } from '../../api-response';

type Session = { id: string; title: string; state: string; created_at: string };
type Report = { title: string; participant_count: number; response_count: number; response_rate: number; questions: { index: number; title: string; responses: number; response_rate: number; accuracy: number | null }[]; individuals: { id: string; nickname: string; score: number; responses: number; accuracy: number | null }[]; hardest: { title: string } | null; easiest: { title: string } | null };
const rate = (value: number) => `${(value * 100).toFixed(1)}%`;
export default function Analytics() {
  const { org } = useParams<{ org: string }>();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selected, setSelected] = useState('');
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState('');
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [loadingReport, setLoadingReport] = useState(false);
  useEffect(() => {
    let active = true; setLoadingSessions(true);
    fetch(`/api/v1/organizations/${org}/sessions`).then(readApiResponse<Session[]>).then(data => { if (active) setSessions(data); }).catch(cause => { if (active) setError(cause.message); }).finally(() => { if (active) setLoadingSessions(false); });
    return () => { active = false; };
  }, [org]);
  useEffect(() => {
    setReport(null); setError('');
    if (!selected) { setLoadingReport(false); return; }
    let active = true; setLoadingReport(true);
    fetch(`/api/v1/sessions/${selected}/analytics`).then(readApiResponse<Report>).then(data => { if (active) setReport(data); }).catch(cause => { if (active) setError(cause.message); }).finally(() => { if (active) setLoadingReport(false); });
    return () => { active = false; };
  }, [selected]);
  return <main className="analytics-page"><header><Link href="/">← Workspace</Link><strong>Session analytics</strong><span className="badge">Insights for your next lesson</span></header><section className="content">
    <div className="page-heading"><div><span className="eyebrow">FROM ANSWERS TO INSIGHT</span><h1>See what landed.</h1><p>Understand participation, celebrate progress and plan what comes next.</p></div></div>
    {error && <p role="alert" className="error">{error}</p>}
    <label className="analytics-selector">Explore a session<select value={selected} disabled={loadingSessions} onChange={event => setSelected(event.target.value)}><option value="">Choose a session</option>{sessions.map(session => <option key={session.id} value={session.id}>{session.title} · {new Date(session.created_at).toLocaleString()} · {session.state}</option>)}</select></label>
    {loadingSessions || loadingReport ? <LoadingSkeleton label={loadingSessions ? 'Loading your sessions…' : 'Preparing your session report…'}/> : !selected && <div className="section-title"><AnimatedEmptyState title={sessions.length ? 'A new perspective on your classroom' : error ? 'Sessions could not load' : 'Your next session tells a story'} icon="chart"><p>{sessions.length ? 'Choose a session to explore participation, question performance and individual results.' : error ? 'Return to the workspace and try again.' : 'Run a live quiz to start collecting classroom insights.'}</p></AnimatedEmptyState></div>}
    {report && <><h2 className="section-title">{report.title}</h2><div className="metric-grid"><FullscreenCard className="panel report-metric" title="Participants"><strong>{report.participant_count}</strong></FullscreenCard><FullscreenCard className="panel report-metric" title="Responses"><strong>{report.response_count}</strong></FullscreenCard><FullscreenCard className="panel report-metric" title="Response rate"><strong>{rate(report.response_rate)}</strong></FullscreenCard></div><FullscreenCard title="Question insights"><p className="analytics-insights"><strong>Hardest:</strong> {report.hardest?.title || 'No scored answers'} · <strong>Easiest:</strong> {report.easiest?.title || 'No scored answers'}</p></FullscreenCard><div className="actions" aria-label="Export report">{['csv', 'xlsx', 'pdf', 'png'].map(format => <a key={format} href={`/api/v1/sessions/${selected}/export/${format}`} className="secondary">Download {format.toUpperCase()}</a>)}</div>
    <FullscreenCard title="Question performance"><div className="table-wrap"><table><thead><tr>{['Question', 'Responses', 'Response rate', 'Accuracy'].map(label => <th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{report.questions.map(question => <tr key={question.index}><td>{question.title}</td><td>{question.responses}</td><td>{rate(question.response_rate)}</td><td>{question.accuracy === null ? 'Not scored' : <>{rate(question.accuracy)}<progress className="analytics-bar" max={1} value={question.accuracy} aria-label={`${question.title}: accuracy`}/></>}</td></tr>)}</tbody></table></div></FullscreenCard>
    <FullscreenCard title="Individual performance"><div className="table-wrap"><table><thead><tr>{['Nickname', 'Responses', 'Score', 'Accuracy'].map(label => <th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{report.individuals.map(participant => <tr key={participant.id}><td>{participant.nickname}</td><td>{participant.responses}</td><td>{participant.score}</td><td>{participant.accuracy === null ? 'Not scored' : rate(participant.accuracy)}</td></tr>)}</tbody></table></div></FullscreenCard></>}
  </section></main>;
}
