'use client';

import { useEffect, useState } from 'react';
import type { QuizQuestion } from './quiz-question';
import { LoadingSkeleton } from './ui-primitives';
import { useDialogFocus } from './use-dialog-focus';

type BankItem = { id: string; question: QuizQuestion; subject: string; topic: string; difficulty: string };
type Props = { org: string; disabled?: boolean; onAdd: (questions: QuizQuestion[]) => void };

const QUESTION_TYPES: Array<{ value: string; label: string }> = [
  { value: 'mcq', label: 'MCQ' },
  { value: 'true_false', label: 'True / False' },
  { value: 'multiple_select', label: 'Multiple Select' },
  { value: 'short_answer', label: 'Short Answer' },
  { value: 'quiz', label: 'Quiz' },
  { value: 'ranking', label: 'Ranking' },
  { value: 'hotspot', label: 'Hotspot' },
  { value: 'poll', label: 'Poll' },
  { value: 'word_cloud', label: 'Word Cloud' },
  { value: 'scale', label: 'Scale' },
  { value: 'rating', label: 'Rating' },
  { value: 'qa', label: 'Q&A' },
  { value: 'survey', label: 'Survey' },
  { value: 'nps', label: 'NPS' },
  { value: 'content', label: 'Content Slide' },
];

const QUICK_FILTER_TYPES = ['mcq', 'true_false', 'multiple_select', 'short_answer', 'quiz'];

function formatKind(kind: string): string {
  return QUESTION_TYPES.find(t => t.value === kind)?.label || kind.replaceAll('_', ' ');
}

export default function QuestionBankPicker({ org, disabled = false, onAdd }: Props) {
  const [open, setOpen] = useState(false);
  const dialogRef = useDialogFocus(open);
  const [items, setItems] = useState<BankItem[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState('');
  const [kind, setKind] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    let active = true;
    setLoading(true);
    fetch(`/api/v1/organizations/${org}/bank/questions`)
      .then(async response => {
        const data = await response.json();
        if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not load the Question Bank.');
        if (active) setItems(data);
      })
      .catch(cause => { if (active) setError((cause as Error).message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [open, org]);

  const availableTypes = Array.from(new Set([
    ...QUESTION_TYPES.map(t => t.value),
    ...items.map(item => item.question.kind),
  ]));
  const chipTypes = Array.from(new Set([
    ...QUICK_FILTER_TYPES,
    ...items.map(item => item.question.kind),
  ]));

  const visible = items.filter(item =>
    (!kind || item.question.kind === kind) &&
    `${item.question.title} ${item.subject} ${item.topic}`.toLowerCase().includes(search.toLowerCase())
  );

  return <>
    <button type="button" className="secondary" disabled={disabled} onClick={() => { setOpen(true); setError(''); }}>From Question Bank</button>
    {open && <div className="ai-overlay"><section ref={dialogRef} tabIndex={-1} className="ai-dialog bank-picker-dialog" role="dialog" aria-modal="true" aria-labelledby="bank-picker-title">
      <header className="ai-dialog-header"><div><span className="eyebrow">PRESENTATION</span><h2 id="bank-picker-title">Add from Question Bank</h2></div>
        <button type="button" className="secondary" onClick={() => setOpen(false)}>Close</button></header>
      <div className="bank-picker-filters">
        <label>Search<input value={search} onChange={event => setSearch(event.target.value)} placeholder="Question, subject, or topic"/></label>
        <label>Question type<select value={kind} onChange={event => setKind(event.target.value)}>
          <option value="">All types</option>
          {availableTypes.map(type => <option key={type} value={type}>{formatKind(type)}</option>)}
        </select></label>
      </div>
      <div className="bank-picker-chips" role="group" aria-label="Filter by question type">
        <button type="button" className={`bank-picker-chip${kind === '' ? ' active' : ''}`} onClick={() => setKind('')}>All</button>
        {chipTypes.map(type => <button key={type} type="button" className={`bank-picker-chip${kind === type ? ' active' : ''}`} onClick={() => setKind(current => current === type ? '' : type)}>{formatKind(type)}</button>)}
      </div>
      {loading && <LoadingSkeleton label="Loading questions…" rows={1}/>}
      {error && <p className="error" role="alert">{error}</p>}
      {!loading && !error && <div className="bank-picker-list">{visible.map(item => <label className="bank-picker-row" key={item.id}>
        <input type="checkbox" checked={selected.has(item.id)} onChange={event => setSelected(current => {
          const next = new Set(current);
          if (event.target.checked) next.add(item.id); else next.delete(item.id);
          return next;
        })}/><span><strong>{item.question.title}</strong><small>{formatKind(item.question.kind)} · {item.subject || 'No subject'} · {item.topic || 'No topic'}</small></span>
      </label>)}{!visible.length && <p>No matching questions are available.</p>}</div>}
      <div className="ai-review-actions"><span>{visible.length} shown · {selected.size} selected</span><button type="button" disabled={!selected.size || loading || Boolean(error)} onClick={() => {
        onAdd(items.filter(item => selected.has(item.id)).map(item => item.question));
        setSelected(new Set());
        setOpen(false);
      }}>Add selected questions</button></div>
    </section></div>}
  </>;
}
