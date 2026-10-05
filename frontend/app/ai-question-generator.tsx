'use client';

import { useEffect, useState } from 'react';
import type { QuizQuestion } from './quiz-question';

type QuestionType = 'mcq' | 'true_false' | 'short_answer' | 'mixed';
type Difficulty = 'easy' | 'medium' | 'hard' | 'mixed';
type SourceType = 'topic' | 'text' | 'image' | 'document';
type GeneratorSettings = {
  question_count: number;
  question_type: QuestionType;
  difficulty: Difficulty;
  language: 'English' | 'Bengali' | 'Hindi';
  grade_level: string;
  subject: string;
  exam_style: string;
};
type GeneratedQuestion = { question: QuizQuestion; difficulty: Exclude<Difficulty, 'mixed'> };
type Draft = GeneratedQuestion & { id: string; selected: boolean };
type Props = {
  org: string;
  disabled?: boolean;
  onSaved?: () => void | Promise<void>;
  onAddToPresentation?: (questions: QuizQuestion[]) => void;
};

const defaultSettings: GeneratorSettings = {
  question_count: 5,
  question_type: 'mcq',
  difficulty: 'medium',
  language: 'English',
  grade_level: '',
  subject: '',
  exam_style: '',
};

function apiError(status: number, data: { detail?: unknown }) {
  if (typeof data.detail === 'string') return data.detail;
  if (status === 401) return 'Sign in to generate questions.';
  if (status === 403) return 'Your account does not have permission to use AI question generation.';
  if (status === 413) return 'The uploaded image is too large.';
  if (status === 415) return 'Upload a valid JPG, PNG, or WEBP image.';
  if (status === 429) return 'The AI generation limit has been reached. Try again later.';
  if (status >= 500) return 'AI question generation is temporarily unavailable. Please try again.';
  return 'Check your source and generation settings, then try again.';
}

export default function AIQuestionGenerator({ org, disabled = false, onSaved, onAddToPresentation }: Props) {
  const [open, setOpen] = useState(false);
  const [sourceType, setSourceType] = useState<SourceType>('topic');
  const [source, setSource] = useState('');
  const [image, setImage] = useState<File | null>(null);
  const [document, setDocument] = useState<File | null>(null);
  const [settings, setSettings] = useState<GeneratorSettings>(defaultSettings);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) setOpen(false);
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [open, busy]);

  function updateSettings<K extends keyof GeneratorSettings>(key: K, value: GeneratorSettings[K]) {
    setSettings(current => ({ ...current, [key]: value }));
  }

  async function requestQuestions(count: number, avoidQuestions: string[], overrides: Partial<GeneratorSettings> = {}) {
    const options = { ...settings, ...overrides, question_count: count, avoid_questions: avoidQuestions };
    let response: Response;
    if (sourceType === 'document') {
      if (!document) throw new Error('Choose a topic document first.');
      if (document.size > 2_000_000) throw new Error('Topic documents must be 2 MB or smaller.');
      const form = new FormData();
      form.set('options_json', JSON.stringify(options));
      form.set('document', document);
      response = await fetch(`/api/v1/organizations/${org}/ai/generate-questions/document`, { method: 'POST', body: form });
    } else if (sourceType === 'image') {
      if (!image) throw new Error('Choose an image to analyze first.');
      const form = new FormData();
      form.set('options_json', JSON.stringify(options));
      form.set('image', image);
      response = await fetch(`/api/v1/organizations/${org}/ai/generate-questions/image`, { method: 'POST', body: form });
    } else {
      if (!source.trim()) throw new Error(sourceType === 'topic' ? 'Enter a topic first.' : 'Paste educational content first.');
      response = await fetch(`/api/v1/organizations/${org}/ai/generate-questions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...options, source_type: sourceType, content: source }),
      });
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(apiError(response.status, data));
    if (!Array.isArray(data.questions)) throw new Error('The AI response could not be validated. Please try again.');
    return (data.questions as GeneratedQuestion[]).map(item => ({
      ...item,
      id: crypto.randomUUID(),
      selected: true,
    }));
  }

  async function runGeneration(action: string, count: number, avoidQuestions: string[], overrides: Partial<GeneratorSettings> = {}) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const result = await requestQuestions(count, avoidQuestions, overrides);
      if (!result.length) throw new Error('No usable questions were generated. Try a different source.');
      return result;
    } catch (cause) {
      setError((cause as Error).message || 'AI question generation failed. Please try again.');
      return null;
    } finally {
      setBusy(false);
      setNotice(action);
    }
  }

  async function generateInitial(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const result = await runGeneration('Review the generated questions before approving them.', settings.question_count, []);
    if (result) setDrafts(result);
  }

  async function generateMore() {
    const count = Math.min(5, 20 - drafts.length);
    if (count < 1) return;
    const result = await runGeneration('More questions are ready for review.', count, drafts.map(item => item.question.title));
    if (result) setDrafts(current => [...current, ...result].slice(0, 20));
  }

  async function regenerateAll() {
    const count = drafts.length;
    if (!count) return;
    const result = await runGeneration('Questions regenerated. Review them before approval.', count, drafts.map(item => item.question.title));
    if (result) setDrafts(result);
  }

  async function regenerateOne(draft: Draft) {
    const result = await runGeneration('Question regenerated. Review it before approval.', 1,
      drafts.map(item => item.question.title),
      { question_type: draft.question.kind as QuestionType, difficulty: draft.difficulty });
    if (result) setDrafts(current => current.map(item => item.id === draft.id ? result[0] : item));
  }

  function editDraft(id: string, patch: Partial<QuizQuestion>) {
    setDrafts(current => current.map(item => item.id === id
      ? { ...item, question: { ...item.question, ...patch } }
      : item));
  }

  async function saveSelected() {
    const selected = drafts.filter(item => item.selected);
    if (!selected.length) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const response = await fetch(`/api/v1/organizations/${org}/bank/questions/bulk`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: selected.map(item => ({
          question: item.question,
          subject: settings.subject,
          topic: sourceType === 'topic' ? source.trim() : settings.subject,
          difficulty: item.difficulty,
          tags: ['ai-generated'],
        })) }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(apiError(response.status, data));
      await onSaved?.();
      setNotice(`${selected.length} question${selected.length === 1 ? '' : 's'} saved to the Question Bank.`);
      setDrafts(current => current.filter(item => !item.selected));
    } catch (cause) {
      setError((cause as Error).message || 'Could not save the selected questions.');
    } finally {
      setBusy(false);
    }
  }

  function addSelectedToPresentation() {
    const selected = drafts.filter(item => item.selected).map(item => item.question);
    if (!selected.length || !onAddToPresentation) return;
    onAddToPresentation(selected);
    setOpen(false);
    setDrafts([]);
    setError('');
    setNotice('');
  }

  const selectedCount = drafts.filter(item => item.selected).length;
  const allSelected = drafts.length > 0 && selectedCount === drafts.length;
  const sourceReady = sourceType === 'document' ? Boolean(document) : sourceType === 'image' ? Boolean(image) : Boolean(source.trim());

  return <>
    <button type="button" className="secondary" disabled={disabled} onClick={() => setOpen(true)}>+ Generate with AI</button>
    {open && <div className="ai-overlay">
      <section className="ai-dialog" role="dialog" aria-modal="true" aria-labelledby="ai-generator-title">
        <header className="ai-dialog-header">
          <div><span className="eyebrow">QUESTION BANK</span><h2 id="ai-generator-title">Generate questions with AI</h2></div>
          <button type="button" className="secondary" disabled={busy} onClick={() => setOpen(false)}>Close</button>
        </header>
        <form className="ai-generator-form" onSubmit={generateInitial}>
          <fieldset className="ai-source-tabs" disabled={busy}>
            <legend>Source</legend>
            {(['topic', 'text', 'document', 'image'] as const).map(mode => <label key={mode}>
              <input type="radio" name="ai-source" checked={sourceType === mode} onChange={() => setSourceType(mode)}/>
              {mode === 'topic' ? 'Topic' : mode === 'text' ? 'Paste text' : mode === 'document' ? 'Upload topic document' : 'Upload image'}
            </label>)}
          </fieldset>
          {sourceType === 'topic' && <label>Topic<input maxLength={500} value={source} onChange={event => setSource(event.target.value)} placeholder="e.g. Human heart" disabled={busy}/></label>}
          {sourceType === 'text' && <label>Educational content<textarea maxLength={20000} rows={5} value={source} onChange={event => setSource(event.target.value)} placeholder="Paste a paragraph, lesson, or notes" disabled={busy}/></label>}
          {sourceType === 'document' && <label className="ai-upload">Topic document<input type="file" accept=".pdf,.pptx,.txt" onChange={event => { setDocument(event.target.files?.[0] ?? null); setError(''); }} disabled={busy}/><span>{document?.name || 'Choose a PDF, PowerPoint (.pptx), or UTF-8 text file'}</span><small>Upload lesson material without an answer key. Maximum 2 MB, 100 pages/slides, and 20,000 characters of text. Then select Generate questions.</small></label>}
          {sourceType === 'image' && <label className="ai-upload">Image<input type="file" accept="image/jpeg,image/png,image/webp" onChange={event => setImage(event.target.files?.[0] ?? null)} disabled={busy}/><span>{image?.name || 'Choose a JPG, PNG, or WEBP image'}</span></label>}

          <div className="ai-settings-grid">
            <label>Question type<select value={settings.question_type} onChange={event => updateSettings('question_type', event.target.value as QuestionType)} disabled={busy}>
              <option value="mcq">MCQ</option><option value="true_false">True / False</option><option value="short_answer">Short Answer</option><option value="mixed">Mixed</option>
            </select></label>
            <label>Difficulty<select value={settings.difficulty} onChange={event => updateSettings('difficulty', event.target.value as Difficulty)} disabled={busy}>
              <option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option><option value="mixed">Mixed</option>
            </select></label>
            <label>Number of questions<input type="number" min={1} max={20} value={settings.question_count} onChange={event => updateSettings('question_count', Math.max(1, Math.min(20, Number(event.target.value) || 1)))} disabled={busy}/></label>
            <label>Language<select value={settings.language} onChange={event => updateSettings('language', event.target.value as GeneratorSettings['language'])} disabled={busy}>
              <option>English</option><option>Bengali</option><option>Hindi</option>
            </select></label>
            <label>Grade / class<input maxLength={120} value={settings.grade_level} onChange={event => updateSettings('grade_level', event.target.value)} disabled={busy}/></label>
            <label>Subject<input maxLength={120} value={settings.subject} onChange={event => updateSettings('subject', event.target.value)} disabled={busy}/></label>
            <label className="ai-exam-style">Exam style<input maxLength={120} placeholder="NEET, JEE, CAT, classroom…" value={settings.exam_style} onChange={event => updateSettings('exam_style', event.target.value)} disabled={busy}/></label>
          </div>
          <button type="submit" disabled={busy || !sourceReady}>{busy ? 'Generating…' : 'Generate questions'}</button>
        </form>

        {busy && <div className="ai-loading" role="status"><span className="ai-spinner"/>Generating questions with AI…</div>}
        {error && <p className="error" role="alert">{error}</p>}
        {!error && notice && <p className="ai-notice" role="status">{notice}</p>}

        {drafts.length > 0 && <section className="ai-review" aria-label="AI generated questions">
          <div className="ai-review-header"><div><h3>AI generated questions</h3><span>{selectedCount} selected · {drafts.length} total</span></div>
            <label className="ai-select-all"><input type="checkbox" checked={allSelected} onChange={event => setDrafts(current => current.map(item => ({ ...item, selected: event.target.checked })))}/>Select all</label>
          </div>
          {drafts.map((draft, index) => <article className="ai-question-card" key={draft.id}>
            <div className="ai-question-card-header"><label><input type="checkbox" checked={draft.selected} onChange={event => setDrafts(current => current.map(item => item.id === draft.id ? { ...item, selected: event.target.checked } : item))}/>Include</label>
              <span>{draft.question.kind.replaceAll('_', ' ')} · {draft.difficulty}</span>
              <button type="button" className="secondary" disabled={busy} onClick={() => regenerateOne(draft)}>Regenerate</button>
              <button type="button" className="secondary" disabled={busy} onClick={() => setDrafts(current => current.filter(item => item.id !== draft.id))}>Delete</button>
            </div>
            <label>Question<textarea rows={2} maxLength={500} value={draft.question.title} onChange={event => editDraft(draft.id, { title: event.target.value })} disabled={busy}/></label>
            {draft.question.body && <label>Supporting text<textarea rows={2} maxLength={5000} value={draft.question.body} onChange={event => editDraft(draft.id, { body: event.target.value })} disabled={busy}/></label>}
            {draft.question.kind !== 'short_answer' && <>
              <label>Options (one per line)<textarea rows={4} value={draft.question.options.join('\n')} onChange={event => {
                const options = event.target.value.split('\n');
                editDraft(draft.id, { options, correct_answers: draft.question.correct_answers.filter(answer => options.includes(answer)) });
              }} disabled={busy || draft.question.kind === 'true_false'}/></label>
              <fieldset className="ai-correct-answers"><legend>Correct answer</legend>{draft.question.options.map(option => <label key={option}>
                <input type="radio" name={`correct-${draft.id}`} checked={draft.question.correct_answers.includes(option)} onChange={() => editDraft(draft.id, { correct_answers: [option] })} disabled={busy}/>{option}
              </label>)}</fieldset>
            </>}
            {draft.question.kind === 'short_answer' && <label>Accepted answers (one per line)<textarea rows={2} value={draft.question.correct_answers.join('\n')} onChange={event => editDraft(draft.id, { correct_answers: event.target.value.split('\n') })} disabled={busy}/></label>}
            <label>Explanation<textarea rows={2} maxLength={3000} value={draft.question.explanation} onChange={event => editDraft(draft.id, { explanation: event.target.value })} disabled={busy}/></label>
            <label>Difficulty<select value={draft.difficulty} onChange={event => setDrafts(current => current.map(item => item.id === draft.id ? { ...item, difficulty: event.target.value as Draft['difficulty'] } : item))} disabled={busy}>
              <option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option>
            </select></label>
            <span className="ai-question-number">Question {index + 1}</span>
          </article>)}
          <div className="ai-review-actions">
            <button type="button" className="secondary" disabled={busy} onClick={regenerateAll}>Regenerate all</button>
            <button type="button" className="secondary" disabled={busy || drafts.length >= 20} onClick={generateMore}>Generate 5 more</button>
            {onAddToPresentation && <button type="button" className="secondary" disabled={busy || !selectedCount} onClick={addSelectedToPresentation}>Add selected to presentation</button>}
            <button type="button" disabled={busy || !selectedCount} onClick={saveSelected}>{busy ? 'Working…' : `Save selected to Question Bank (${selectedCount})`}</button>
          </div>
        </section>}
      </section>
    </div>}
  </>;
}
