'use client';
import { useState } from 'react';
import { readApiResponse } from './api-response';
import { QuestionTypeBadge } from './ui-primitives';
import { HotspotInput, type Pin } from './live-formats';
type Review={title:string;score:number;questions:{index:number;kind:string;title:string;body:string;options:string[];correct_answers:string[];explanation:string;model_answer?:string;image_url?:string;image_alt?:string;hotspot_target?:Pin & {radius:number};answer:string|number|string[]|Pin|null;correct:boolean|null;score:number;marks:number;status:string}[]};
export default function ResultsPreview({url,token}:{url:string;token?:string}){
  const [results,setResults]=useState<Review|null>(null);const [open,setOpen]=useState(false);const [busy,setBusy]=useState(false);const [error,setError]=useState('');
  async function preview(){if(open){setOpen(false);return;}setBusy(true);setError('');try{const r=await fetch(url,{cache:'no-store',headers:token?{'X-Participant-Token':token}:{}});setResults(await readApiResponse<Review>(r));setOpen(true);}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  return <section className="results-preview"><button onClick={preview} disabled={busy} aria-expanded={open}>{busy?'Loading results…':open?'Hide preview':'Preview answers'}</button>{error&&<p role="alert" className="error">{error}</p>}{open&&results&&<div><h2>Answer review</h2><p>Your score: {results.score/1000} marks</p>{results.questions.map(q=>{
    const selected=Array.isArray(q.answer)?q.answer:q.answer===null?[]:[String(q.answer)];
    return <article className="panel" key={q.index}><QuestionTypeBadge kind={q.kind}/><h3>{q.index+1}. {q.title}</h3><p>{q.body}</p><p><strong>{q.status==='incorrect'?'Incorrect':q.status==='correct'?'Correct':q.status==='unanswered'?'Not answered':'Not graded'}</strong> · {q.score/1000} marks</p>
      {q.kind==='hotspot'?<HotspotInput url={q.image_url||''} alt={q.image_alt||''} value={q.answer&&typeof q.answer==='object'&&!Array.isArray(q.answer)?q.answer:null} target={q.hotspot_target}/>:q.kind==='ranking'?<><p>Your order: {selected.join(' → ')||'Not answered'}</p>{q.correct_answers.length>0&&<p>Correct order: {q.correct_answers.join(' → ')}</p>}</>:q.options.length>0?<ul className="review-options">{q.options.map(option=>{
        const right=q.correct_answers.includes(option);const chosen=selected.includes(option);
        return <li key={option} className={right?'review-correct':chosen&&q.correct===false?'review-wrong':''}><span>{option}</span><strong>{right?(chosen?'Correct answer · Your answer':'Correct answer'):chosen?(q.correct===false?'Your answer · Incorrect':'Your answer'):''}</strong></li>;
      })}</ul>:<><p>Your answer: {selected.join(', ')||'Not answered'}</p>{q.correct_answers.length>0&&<p className="review-correct">Accepted answers: {q.correct_answers.join(', ')}</p>}</>}
      {q.model_answer&&<p><strong>Model answer:</strong> {q.model_answer}</p>}
      {q.explanation&&<p><strong>Explanation:</strong> {q.explanation}</p>}
    </article>;
  })}</div>}</section>;
}
