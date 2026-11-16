'use client';

import { useEffect, useState } from 'react';
import { authFetch } from './auth-fetch';
import type { QuizQuestion } from './quiz-question';
import { LoadingSkeleton } from './ui-primitives';
import { useDialogFocus } from './use-dialog-focus';

type BankItem = { id: string; question: QuizQuestion; subject: string; topic: string; difficulty: string };
type Props = { org: string; disabled?: boolean; onAdd: (questions: QuizQuestion[]) => void };

function formatKind(kind: string): string {
  const k = (kind || 'mcq').toLowerCase();
  if (k === 'mcq' || k === 'quiz') return 'MCQ';
  if (k === 'true_false') return 'True / False';
  return kind.replaceAll('_', ' ');
}

function matchesKind(itemKind: string | undefined, selected: string): boolean {
  if (!selected) return true;
  const k = (itemKind || 'mcq').toLowerCase();
  if (selected === 'mcq') return k === 'mcq' || k === 'quiz';
  if (selected === 'true_false') return k === 'true_false';
  if (selected === 'other') return k !== 'mcq' && k !== 'quiz' && k !== 'true_false';
  return k === selected;
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
    authFetch(`/api/v1/organizations/${org}/bank/questions`)
      .then(async response => {
        const data = await response.json();
        if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not load the Question Bank.');
        if (active) setItems(data);
      })
      .catch(cause => { if (active) setError((cause as Error).message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [open, org]);

  const visible = items.filter(item =>
    matchesKind(item.question?.kind, kind) &&
    `${item.question?.title || ''} ${item.subject || ''} ${item.topic || ''}`.toLowerCase().includes(search.toLowerCase())
  );

  return <>
    <button type="button" className="secondary" disabled={disabled} onClick={() => { setOpen(true); setError(''); setSearch(''); setKind(''); }}>From Question Bank</button>
    {open && <div className="ai-overlay"><section ref={dialogRef} tabIndex={-1} className="ai-dialog bank-picker-dialog" role="dialog" aria-modal="true" aria-labelledby="bank-picker-title">
      <header className="ai-dialog-header"><div><span className="eyebrow">PRESENTATION</span><h2 id="bank-picker-title">Add from Question Bank</h2></div>
        <button type="button" className="secondary" onClick={() => setOpen(false)}>Close</button></header>
      <div className="bank-picker-filters">
        <label>Search<input value={search} onChange={event => setSearch(event.target.value)} placeholder="Question, subject, or topic"/></label>
        <label>Question type<select value={kind} onChange={event => setKind(event.target.value)}>
          <option value="">All types</option>
          <option value="mcq">MCQ</option>
          <option value="true_false">True / False</option>
          <option value="other">Other</option>
        </select></label>
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
