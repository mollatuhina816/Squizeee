'use client';

import { useEffect, useState } from 'react';
import type { QuizQuestion } from './quiz-question';

type BankItem = { id: string; question: QuizQuestion; subject: string; topic: string; difficulty: string };
type Props = { org: string; disabled?: boolean; onAdd: (questions: QuizQuestion[]) => void };

export default function QuestionBankPicker({ org, disabled = false, onAdd }: Props) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<BankItem[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState('');
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

  const visible = items.filter(item => `${item.question.title} ${item.subject} ${item.topic}`.toLowerCase().includes(search.toLowerCase()));

  return <>
    <button type="button" className="secondary" disabled={disabled} onClick={() => { setOpen(true); setError(''); }}>From Question Bank</button>
    {open && <div className="ai-overlay"><section className="ai-dialog bank-picker-dialog" role="dialog" aria-modal="true" aria-labelledby="bank-picker-title">
      <header className="ai-dialog-header"><div><span className="eyebrow">PRESENTATION</span><h2 id="bank-picker-title">Add from Question Bank</h2></div>
        <button type="button" className="secondary" onClick={() => setOpen(false)}>Close</button></header>
      <label>Search<input value={search} onChange={event => setSearch(event.target.value)} placeholder="Question, subject, or topic"/></label>
      {loading && <p role="status">Loading questions…</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {!loading && !error && <div className="bank-picker-list">{visible.map(item => <label className="bank-picker-row" key={item.id}>
        <input type="checkbox" checked={selected.has(item.id)} onChange={event => setSelected(current => {
          const next = new Set(current);
          if (event.target.checked) next.add(item.id); else next.delete(item.id);
          return next;
        })}/><span><strong>{item.question.title}</strong><small>{item.question.kind.replaceAll('_', ' ')} · {item.subject || 'No subject'} · {item.topic || 'No topic'}</small></span>
      </label>)}{!visible.length && <p>No matching questions are available.</p>}</div>}
      <div className="ai-review-actions"><span>{selected.size} selected</span><button type="button" disabled={!selected.size || loading || Boolean(error)} onClick={() => {
        onAdd(items.filter(item => selected.has(item.id)).map(item => item.question));
        setSelected(new Set());
        setOpen(false);
      }}>Add selected questions</button></div>
    </section></div>}
  </>;
}