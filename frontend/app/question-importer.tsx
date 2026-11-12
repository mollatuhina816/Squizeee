'use client';
import { useEffect, useState } from 'react';
import { readApiResponse } from './api-response';
import { ProcessingIndicator } from './ui-primitives';
type CanonicalQuestion={type:string;question:string;options?:{id:string;text:string}[];correct_answers?:string[];accepted_answers?:string[];model_answer?:string;explanation?:string;answer_origin?:string;requires_review?:boolean;source?:{filename?:string;slide_number?:number;page_number?:number;row_number?:number;sections?:number[]};[key:string]:unknown};
type Document={schema_version:'1.0';questions:CanonicalQuestion[]};
type Preview={id:string;rows:{requires_review?:boolean;canonical:CanonicalQuestion}[];document:Document;errors:{row:number;message:string}[];can_commit:boolean;review_count:number;detected_format?:string};
const types=['mcq','multiple_select','true_false','short_answer','survey','poll','ranking','scale','rating','nps','word_cloud','quiz','qa','form','content'];
const scored=(type:string)=>['mcq','multiple_select','true_false','quiz'].includes(type);
const choices=(type:string)=>scored(type)||['survey','poll','ranking'].includes(type);
function changeType(item:CanonicalQuestion,type:string):CanonicalQuestion{
 const next:CanonicalQuestion={...item,type};delete next.correct_answers;delete next.accepted_answers;delete next.model_answer;delete next.options;delete next.minimum;delete next.maximum;
 if(choices(type))next.options=type==='true_false'?[{id:'True',text:'True'},{id:'False',text:'False'}]:item.options?.length?item.options:[{id:'A',text:''},{id:'B',text:''}];
 if(scored(type))next.correct_answers=[];
 if(type==='short_answer')next.accepted_answers=[];
 if(['scale','rating','nps'].includes(type)){next.minimum=type==='nps'?0:1;next.maximum=type==='nps'?10:5;}
 return next;
}
export default function QuestionImporter<T>({org,presentationId,beforeImport,onImported,onBusyChange}:{org:string;presentationId?:string;beforeImport?:()=>Promise<number|null>;onBusyChange?:(busy:boolean)=>void;onImported:(result:{questions?:T[];revision?:number})=>void}){
 const [preview,setPreview]=useState<Preview|null>(null),[questions,setQuestions]=useState<CanonicalQuestion[]>([]),[dirty,setDirty]=useState(false),[advanced,setAdvanced]=useState<string|null>(null),[acknowledged,setAcknowledged]=useState(false);
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
 useEffect(()=>{onBusyChange?.(busy);},[busy,onBusyChange]);
 function install(data:Preview){setPreview(data);setQuestions(data.document.questions);setDirty(false);setAdvanced(null);setAcknowledged(false);}
 function edit(index:number,patch:Partial<CanonicalQuestion>){setQuestions(old=>old.map((q,i)=>i===index?{...q,...patch}:q));setDirty(true);setAdvanced(null);}
 async function upload(file:File){setBusy(true);setPreview(null);setError('');setMessage('');try{
  if(file.size>40000000)throw Error('Maximum upload size is 40 MB.');
  const data=new FormData();data.set('file',file);
  const r=await fetch(`/api/v1/organizations/${org}/imports/preview/file`,{method:'POST',body:data});install(await readApiResponse<Preview>(r));
 }catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function approve(){if(!preview)return;setBusy(true);setError('');try{
  const document:Document=advanced===null?{schema_version:'1.0',questions}:JSON.parse(advanced);
  const r=await fetch(`/api/v1/organizations/${org}/imports/${preview.id}/review`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({document,acknowledge_unresolved:acknowledged})});
  install(await readApiResponse<Preview>(r));setMessage('Faculty review saved. You can now import the approved questions.');
 }catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function suggest(index:number){if(!preview)return;setBusy(true);setError('');try{
  const r=await fetch(`/api/v1/organizations/${org}/imports/${preview.id}/questions/${index}/suggest-answer`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:questions[index]})});
  const data=await readApiResponse<{answers:string[];explanation:string}>(r);
  edit(index,{...(questions[index].type==='short_answer'?{accepted_answers:data.answers}:{correct_answers:data.answers}),explanation:data.explanation,answer_origin:'ai_suggested',requires_review:true});
  setMessage('AI-suggested answer is unverified. Check it before saving faculty approval.');
 }catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function commit(){if(!preview)return;setBusy(true);setError('');try{
  const revision=presentationId?await beforeImport?.():undefined;
  if(presentationId&&!revision)throw Error('Save the current questions successfully before importing.');
  const path=presentationId?`presentation/${presentationId}`:'commit';
  const r=await fetch(`/api/v1/organizations/${org}/imports/${preview.id}/${path}`,{method:'POST',headers:{'Content-Type':'application/json'},body:presentationId?JSON.stringify({revision}):undefined});
  onImported(await readApiResponse<{questions?:T[];revision?:number}>(r));setMessage(`${preview.rows.length} approved questions imported.`);setPreview(null);
 }catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 return <section className="panel question-importer"><h2>Import questions from a file</h2><p>PDF, DOCX, PPTX, XLSX, CSV, TXT or JSON | maximum 40 MB.</p>
 <details><summary>Supported formats and answer review</summary><p>Upload the original document. PowerPoint extraction reads text boxes, groups, tables, speaker notes and slide order. Gemini can interpret difficult layouts and embedded images; full slide rendering uses the configured rendering service.</p><p>Missing answers stay blank for faculty review. AI answer suggestions are a separate, unverified action. Older DOC, PPT and XLS files require the configured conversion service or an exported DOCX, PPTX, XLSX or PDF.</p><p>Spreadsheets can use question/title, type/kind, options separated by | or individual option columns, and optional correct_answers. JSON uses schema_version 1.0 and type-specific questions. Plain text and documents may contain numbered questions and separate answer keys.</p></details>
 <label>Choose question file<input type="file" accept=".pdf,.docx,.pptx,.xlsx,.csv,.txt,.json,.doc,.ppt,.xls,.odt,.odp,.rtf" disabled={busy} onChange={e=>{const f=e.target.files?.[0];if(f)void upload(f);e.target.value='';}}/></label>
 {busy&&<ProcessingIndicator>Processing your document</ProcessingIndicator>}{error&&<p role="alert" className="error">{error}</p>}{message&&<p role="status">{message}</p>}
 {preview&&<div><h3>Review extracted questions</h3><p>{questions.length} questions | {preview.review_count} require review | {preview.errors.length} extraction issues{preview.detected_format?` | detected ${preview.detected_format.toUpperCase()}`:''}.</p>
 {preview.errors.map((e,i)=><p className="error" key={i}>{e.row?`Question/row ${e.row}: `:''}{e.message}</p>)}
 <ol>{questions.map((q,i)=><li key={i}><fieldset disabled={busy}><legend>Question {i+1}{q.requires_review?' | Faculty review required':''}</legend>
 <p>{q.source?.filename}{q.source?.slide_number?` | Slide ${q.source.slide_number}`:q.source?.page_number?` | Page ${q.source.page_number}`:q.source?.row_number?` | Row ${q.source.row_number}`:''}{(q.source?.sections?.length||0)>1?` | Spans sections ${q.source!.sections!.join(', ')}`:''}</p>
 <label>Question type<select value={q.type} onChange={e=>edit(i,changeType(q,e.target.value))}>{types.map(type=><option key={type} value={type}>{type.replaceAll('_',' ')}</option>)}</select></label>
 <label>Question<textarea maxLength={500} value={q.question} onChange={e=>edit(i,{question:e.target.value})}/></label>
 {q.options?.map((o,j)=><div key={o.id}><label>{o.id}<input maxLength={300} value={o.text} onChange={e=>edit(i,{options:q.options!.map((v,k)=>j===k?{...v,text:e.target.value}:v)})}/></label>{scored(q.type)&&<label><input type="checkbox" checked={q.correct_answers?.includes(o.id)||false} onChange={e=>edit(i,{correct_answers:e.target.checked?q.type==='multiple_select'?[...(q.correct_answers||[]),o.id]:[o.id]:(q.correct_answers||[]).filter(a=>a!==o.id),answer_origin:'faculty'})}/>Correct answer</label>}</div>)}
 {q.type==='short_answer'&&<><label>Accepted answers (one per line; optional for an ungraded response)<textarea value={q.accepted_answers?.join('\n')||''} onChange={e=>edit(i,{accepted_answers:e.target.value.split('\n').filter(a=>a.trim()),answer_origin:'faculty'})}/></label><label>Model answer (optional)<textarea value={q.model_answer||''} onChange={e=>edit(i,{model_answer:e.target.value})}/></label></>}
 {q.answer_origin==='ai_suggested'&&<p role="status">AI-suggested answer | unverified. Faculty approval is required.</p>}
 {scored(q.type)&&!q.correct_answers?.length&&<p className="error">No explicit correct answer found. Select an answer after checking the source.</p>}
 <label>Explanation (optional)<textarea maxLength={3000} value={q.explanation||''} onChange={e=>edit(i,{explanation:e.target.value})}/></label>
 {(scored(q.type)||q.type==='short_answer')&&i<preview.rows.length&&<button type="button" className="secondary" onClick={()=>void suggest(i)}>Generate/Verify Answer with AI</button>}
 </fieldset></li>)}</ol>
 <details><summary>Review canonical JSON / resolve unmatched questions</summary><p>You can correct options, ranges, source associations or add missing questions here. All questions are validated again before approval.</p><textarea aria-label="Canonical question JSON" rows={15} disabled={busy} value={advanced??JSON.stringify({schema_version:'1.0',questions},null,2)} onChange={e=>{setAdvanced(e.target.value);setDirty(true);}}/></details>
 {!!preview.errors.length&&<label><input type="checkbox" checked={acknowledged} disabled={busy} onChange={e=>setAcknowledged(e.target.checked)}/>I checked the original document and resolved the reported unmatched or unsupported content in this preview.</label>}
 <button type="button" disabled={busy||!!preview.errors.length&&!acknowledged} onClick={()=>void approve()}>Save faculty approval</button>
 <button disabled={busy||dirty||!preview.can_commit} onClick={()=>void commit()}>Import into {presentationId?'this quiz':'question bank'}</button>
 </div>}</section>;
}
