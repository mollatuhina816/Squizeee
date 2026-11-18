'use client';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import '../../session-records.css';
import FullscreenCard from '../../fullscreen-card';
import { useEffect, useState } from 'react';
import { AnimatedEmptyState, LoadingSkeleton } from '../../ui-primitives';
import { readApiResponse } from '../../api-response';

type Session = { record_type:'live'|'assigned'; id: string; title: string; state: string; created_at: string };
type AnswerDetail={index:number;title:string;kind:string;body:string;options:string[];answer:unknown;correct_answers:string[];explanation:string;model_answer:string;status:string;score:number;marks:number;elapsed_ms?:number|null};
const displayAnswer=(answer:unknown):string=>answer===null||answer===undefined?'No answer':Array.isArray(answer)?answer.map(displayAnswer).join(', '):typeof answer==='object'?JSON.stringify(answer):String(answer);
type Report = { record_type:'live'|'assigned'; title: string; participant_count: number; response_count: number; response_rate: number; questions: { index: number; title: string; responses: number; response_rate: number; accuracy: number | null }[]; individuals: { id: string; nickname: string; email?:string;status?:string;right_count:number;wrong_count:number;unanswered_count:number;ungraded_count:number;questions:AnswerDetail[]; score: number; responses: number; accuracy: number | null }[]; hardest: { title: string } | null; easiest: { title: string } | null };
const rate = (value: number) => `${(value * 100).toFixed(1)}%`;
export default function Analytics() {
  const { org } = useParams<{ org: string }>();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selected, setSelected] = useState('');
  const [studentQuery,setStudentQuery]=useState('');
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
    const record=sessions.find(item=>item.id===selected);
    fetch(`/api/v1/${record?.record_type==='assigned'?'scheduled-quizzes':'sessions'}/${selected}/analytics`).then(readApiResponse<Report>).then(data => { if (active) setReport(data); }).catch(cause => { if (active) setError(cause.message); }).finally(() => { if (active) setLoadingReport(false); });
    return () => { active = false; };
  }, [selected,sessions]);
  return <main className="analytics-page"><header><Link href="/">← Workspace</Link><strong>Session records</strong><span className="badge">Insights for your next lesson</span></header><section className="content">
    <div className="page-heading"><div><span className="eyebrow">FROM ANSWERS TO INSIGHT</span><h1>Your classroom session records.</h1><p>Review live sessions and assigned quizzes, student scores, and every right or wrong answer.</p></div></div>
    {error && <p role="alert" className="error">{error}</p>}
    <label className="analytics-selector">Explore a session<select value={selected} disabled={loadingSessions} onChange={event => setSelected(event.target.value)}><option value="">Choose a session</option>{sessions.map(session => <option key={session.id} value={session.id}>{session.record_type==='assigned'?'Assigned quiz':'Live session'} | {session.title} · {new Date(session.created_at).toLocaleString()} · {session.state}</option>)}</select></label>
    {loadingSessions || loadingReport ? <LoadingSkeleton label={loadingSessions ? 'Loading your sessions…' : 'Preparing your session report…'}/> : !selected && <div className="section-title"><AnimatedEmptyState title={sessions.length ? 'A new perspective on your classroom' : error ? 'Sessions could not load' : 'Your next session tells a story'} icon="chart"><p>{sessions.length ? 'Choose a session to explore participation, question performance and individual results.' : error ? 'Return to the workspace and try again.' : 'Run a live session or assign a quiz to start collecting student records.'}</p></AnimatedEmptyState></div>}
    {report && <><h2 className="section-title">{report.title}</h2><div className="metric-grid"><FullscreenCard className="panel report-metric" title="Participants"><strong>{report.participant_count}</strong></FullscreenCard><FullscreenCard className="panel report-metric" title="Responses"><strong>{report.response_count}</strong></FullscreenCard><FullscreenCard className="panel report-metric" title="Response rate"><strong>{rate(report.response_rate)}</strong></FullscreenCard></div><FullscreenCard title="Question insights"><p className="analytics-insights"><strong>Hardest:</strong> {report.hardest?.title || 'No scored answers'} · <strong>Easiest:</strong> {report.easiest?.title || 'No scored answers'}</p></FullscreenCard>{report.record_type==='live'&&<div className="actions" aria-label="Export report">{['csv', 'xlsx', 'pdf', 'png'].map(format => <a key={format} href={`/api/v1/sessions/${selected}/export/${format}`} className="secondary">Download {format.toUpperCase()}</a>)}</div>}
    <FullscreenCard title="Question performance"><div className="table-wrap"><table><thead><tr>{['Question', 'Responses', 'Response rate', 'Accuracy'].map(label => <th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{report.questions.map(question => <tr key={question.index}><td>{question.title}</td><td>{question.responses}</td><td>{rate(question.response_rate)}</td><td>{question.accuracy === null ? 'Not scored' : <>{rate(question.accuracy)}<progress className="analytics-bar" max={1} value={question.accuracy} aria-label={`${question.title}: accuracy`}/></>}</td></tr>)}</tbody></table></div></FullscreenCard>
    <section className="panel student-session-records"><div className="student-records-heading"><div><h2>Student performance &amp; answer details</h2><p>Expand a student to see their answers, the correct answers, and marks for each question.</p></div><label>Search students<input type="search" value={studentQuery} onChange={e=>setStudentQuery(e.target.value)} placeholder="Name or email"/></label></div>
    {report.record_type==='assigned'&&<p>In-progress answers and scores are provisional. Not-started students are included.</p>}
    {!report.individuals.length&&<p>No students have joined or been assigned to this record.</p>}
    {report.individuals.filter(p=>`${p.nickname} ${p.email||''}`.toLowerCase().includes(studentQuery.toLowerCase())).map(participant=><details className="student-record" key={participant.id}><summary><span className="student-record-name"><strong>{participant.nickname}</strong><small>{participant.email}{participant.status?` | ${participant.status}`:''}</small></span><span className="student-record-score">{participant.score} marks</span><span className="answer-count right">{participant.right_count} right</span><span className="answer-count wrong">{participant.wrong_count} wrong</span><span className="answer-count">{participant.unanswered_count} unanswered</span><span className="answer-count">{participant.ungraded_count} ungraded</span></summary><div className="student-record-body"><p>Responses: {participant.responses} | Accuracy: {participant.accuracy===null?'Not scored':rate(participant.accuracy)}</p><div className="table-wrap"><table><thead><tr>{['Question','Student answer','Correct answer','Result','Marks earned'].map(label=><th key={label} scope="col">{label}</th>)}</tr></thead><tbody>{participant.questions.map(q=><tr key={q.index}><td><strong>{q.index+1}. {q.title}</strong>{q.body&&<p>{q.body}</p>}{q.options.length>0&&<details><summary>View options</summary><ol type="A">{q.options.map((option,i)=><li key={i}>{option}</li>)}</ol></details>}{q.explanation&&<p><strong>Explanation:</strong> {q.explanation}</p>}</td><td>{displayAnswer(q.answer)}</td><td>{q.correct_answers.length?q.correct_answers.join(', '):q.model_answer|| (q.kind==='hotspot'?'See hotspot target in quiz editor':'Not automatically graded')}</td><td><span className={`answer-result ${q.status}`}>{q.status==='incorrect'?'Wrong':q.status==='correct'?'Right':q.status}</span></td><td>{q.score/1000}<small>Base marks: {q.marks/1000}</small>{q.elapsed_ms!==null&&q.elapsed_ms!==undefined&&<small>{(q.elapsed_ms/1000).toFixed(1)} seconds</small>}</td></tr>)}</tbody></table></div></div></details>)}
    {!!report.individuals.length&&!report.individuals.some(p=>`${p.nickname} ${p.email||''}`.toLowerCase().includes(studentQuery.toLowerCase()))&&<p>No students match your search.</p>}
    </section></>}
  </section></main>;
}
