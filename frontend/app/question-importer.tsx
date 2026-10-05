'use client';
import { useEffect, useState } from 'react';
import { readApiResponse } from './api-response';
type Extracted={title:string;kind:string;options:string[];correct_answers:string[];explanation:string};
type Preview={id:string;rows:{question:Extracted}[];errors:{row:number;message:string}[];can_commit:boolean};
export default function QuestionImporter<T>({org,presentationId,beforeImport,onImported,onBusyChange}:{org:string;presentationId?:string;beforeImport?:()=>Promise<number|null>;onBusyChange?:(busy:boolean)=>void;onImported:(result:{questions?:T[];revision?:number})=>void}){
  const [preview,setPreview]=useState<Preview|null>(null);const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [message,setMessage]=useState('');
  useEffect(()=>{onBusyChange?.(busy);},[busy,onBusyChange]);
  async function upload(file:File){setBusy(true);setPreview(null);setError('');setMessage('');try{
    if(file.size>2000000)throw Error('Maximum upload size is 2 MB.');
    const format=file.name.split('.').pop()?.toLowerCase();
    if(format==='ppt')throw Error('Save the old .ppt file as .pptx in PowerPoint, then upload it.');
    if(!format||!['pdf','pptx','csv','xlsx'].includes(format))throw Error('Choose PDF, PPTX, CSV or XLSX.');
    const content_base64=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('Unable to read this file'));reader.readAsDataURL(file);});
    const r=await fetch(`/api/v1/organizations/${org}/imports/preview`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({format,content_base64})});
    setPreview(await readApiResponse<Preview>(r));
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  async function commit(){if(!preview)return;setBusy(true);setError('');try{
    const revision=presentationId?await beforeImport?.():undefined;
    if(presentationId&&!revision)throw Error('Save the current questions successfully before importing.');
    const path=presentationId?`presentation/${presentationId}`:'commit';
    const r=await fetch(`/api/v1/organizations/${org}/imports/${preview.id}/${path}`,{method:'POST',headers:{'Content-Type':'application/json'},body:presentationId?JSON.stringify({revision}):undefined});
    const result=await readApiResponse<{questions?:T[];revision?:number}>(r);onImported(result);setMessage(`${preview.rows.length} questions imported with their correct answers.`);setPreview(null);
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  return <section className="panel"><h2>Import questions from a file</h2><p>PDF, PowerPoint (.pptx), CSV or XLSX · maximum 2 MB. PDF/PowerPoint: up to 100 questions and 100 pages/slides.</p><details><summary>File format and answer-key instructions</summary><p>Use selectable text, lettered options and an explicit answer. Keep each question on one PDF page or PowerPoint slide; numbered questions can share a page. PowerPoint answers may also be in speaker notes.</p><pre>{'Question 1: What is the capital of France?\nA) Paris\nB) London\nC) Rome\nAnswer: A\nExplanation: Paris is the capital of France.\nMarks: 1'}</pre><p>Use <code>Answer: A, C</code> for multiple correct answers. Scanned PDFs need OCR first. Save older .ppt files as .pptx. Separate answer-key pages and answers indicated only by color are not supported.</p><p>CSV/XLSX: headers kind, title, options, correct_answers. Separate options and answers with |.</p></details><label>Choose question file<input type="file" accept=".pdf,.pptx,.ppt,.csv,.xlsx" disabled={busy} onChange={e=>{const f=e.target.files?.[0];if(f)upload(f);e.target.value='';}}/></label>{busy&&<p role="status">Processing…</p>}{error&&<p role="alert" className="error">{error}</p>}{message&&<p role="status">{message}</p>}{preview&&<div><h3>Review extracted questions</h3><p>{preview.rows.length} valid questions · {preview.errors.length} errors. Check the answer key before importing.</p>{preview.errors.map((e,i)=><p className="error" key={i}>Question/row {e.row}: {e.message}</p>)}<ol>{preview.rows.map((r,i)=><li key={i}><strong>{r.question.title}</strong><ul>{r.question.options.map((option,j)=><li key={j}>{option}{r.question.correct_answers.includes(option)?' — Correct answer':''}</li>)}</ul><p>Correct answer(s): {r.question.correct_answers.join(', ')}</p>{r.question.explanation&&<p>Explanation: {r.question.explanation}</p>}</li>)}</ol><button disabled={busy||!preview.can_commit} onClick={commit}>Import into {presentationId?'this quiz':'question bank'}</button></div>}</section>;
}
