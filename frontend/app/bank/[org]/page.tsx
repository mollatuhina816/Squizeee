'use client';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import QuestionImporter from '../../question-importer';
import AIQuestionGenerator from '../../ai-question-generator';
import { AnimatedEmptyState, LoadingSkeleton, QuestionTypeBadge } from '../../ui-primitives';
import { readApiResponse } from '../../api-response';
import { useCallback, useEffect, useState } from 'react';

type BankItem = { id: string; question: { title: string; kind: string; body?: string; options?: string[] }; subject: string; chapter: string; topic: string; difficulty: string };
export default function Bank() {
  const { org } = useParams<{ org: string }>();
  const [items, setItems] = useState<BankItem[]>([]);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [kind, setKind] = useState('');
  const [loading, setLoading] = useState(true);
  const refresh = useCallback(async () => {
    setLoading(true); setError('');
    try { setItems(await fetch(`/api/v1/organizations/${org}/bank/questions`).then(readApiResponse<BankItem[]>)); }
    catch (cause) { setError((cause as Error).message); }
    finally { setLoading(false); }
  }, [org]);
  useEffect(() => { void refresh(); }, [refresh]);
  const visible = items.filter(item => (!kind || item.question.kind === kind) && `${item.question.title} ${item.subject} ${item.chapter} ${item.topic}`.toLowerCase().includes(search.toLowerCase()));
  return <main className="bank-page"><header><Link href="/">← Workspace</Link><strong>Question bank</strong><span className="badge">Your teaching toolkit</span></header><section className="content">
    <div className="page-heading"><div><span className="eyebrow">BUILD ON GOOD IDEAS</span><h1>Good questions, ready to reuse.</h1><p>A thoughtful library for your next lesson. Import, generate and explore.</p></div></div>
    {error && <p role="alert" className="error">{error}</p>}
    <div className="bank-actions"><QuestionImporter org={org} onImported={() => { void refresh(); }}/><AIQuestionGenerator org={org} onSaved={refresh}/></div>
    <div className="toolbar bank-filters"><strong>{items.length} questions <span className="count">{visible.length} shown</span></strong><label className="bank-search">Search questions<input placeholder="Question, subject, chapter or topic" value={search} onChange={event => setSearch(event.target.value)}/></label><label>Question type<select value={kind} onChange={event => setKind(event.target.value)}><option value="">All types</option>{Array.from(new Set(items.map(item => item.question.kind))).sort().map(type => <option key={type} value={type}>{type.replaceAll('_', ' ')}</option>)}</select></label></div>
    {loading ? <LoadingSkeleton label="Loading your question library…"/> : !items.length ? <AnimatedEmptyState title={error ? 'Your library could not load' : 'A great lesson starts with a question'}><p>{error ? 'Please try loading the library again.' : 'Save questions from the editor or import a question file to begin.'}</p>{error && <button onClick={() => void refresh()}>Retry loading</button>}</AnimatedEmptyState> : !visible.length ? <AnimatedEmptyState title="No matching questions"><p>Try another search or choose a different question type.</p><button className="secondary" onClick={() => { setSearch(''); setKind(''); }}>Clear filters</button></AnimatedEmptyState> : <div className="bank-grid">{visible.map(item => <article className="bank-question" key={item.id}><QuestionTypeBadge kind={item.question.kind}/><h2>{item.question.title}</h2><p>{item.subject || 'No subject'}{item.chapter ? ` / ${item.chapter}` : ''}{item.topic ? ` / ${item.topic}` : ''}</p><div className="bank-question-meta"><span className="badge">{item.difficulty}</span></div><details><summary>Preview question</summary>{item.question.body && <p>{item.question.body}</p>}{!!item.question.options?.length && <ul>{item.question.options.map(option => <li key={option}>{option}</li>)}</ul>}{!item.question.body && !item.question.options?.length && <p>This question has no supporting text or options.</p>}</details></article>)}</div>}
  </section></main>;
}
