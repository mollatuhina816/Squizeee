'use client';
import { useEffect, useState } from 'react';
import { readApiResponse } from './api-response';
import { ProcessingIndicator } from './ui-primitives';
import './question-importer.css';
type CanonicalQuestion={type:string;question:string;body?:string;options?:{id:string;text:string}[];correct_answers?:string[];accepted_answers?:string[];model_answer?:string;explanation?:string;answer_origin?:string;requires_review?:boolean;source?:{answer_evidence?:string;filename?:string;slide_number?:number;page_number?:number;row_number?:number;sections?:number[]};[key:string]:unknown};
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
 const [method,setMethod]=useState<'ai'|'structured'>('ai'),[fileType,setFileType]=useState('pdf'),[selectedFile,setSelectedFile]=useState<File|null>(null);
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
 useEffect(()=>{onBusyChange?.(busy);},[busy,onBusyChange]);
 function chooseMethod(next:'ai'|'structured'){setMethod(next);setPreview(null);setSelectedFile(null);setError('');setMessage('');}
 function install(data:Preview){setPreview(data);setQuestions(data.document.questions);setDirty(false);setAdvanced(null);setAcknowledged(false);}
 function edit(index:number,patch:Partial<CanonicalQuestion>){setQuestions(old=>old.map((q,i)=>i===index?{...q,...patch}:q));setDirty(true);setAdvanced(null);}
 async function upload(file:File){setBusy(true);setPreview(null);setError('');setMessage('');try{
  if(file.size>40000000)throw Error('Maximum upload size is 40 MB.');
  const data=new FormData();data.set('file',file);
  const r=await fetch(`/api/v1/organizations/${org}/imports/${method==='structured'?'structured/':''}preview/file`,{method:'POST',body:data});install(await readApiResponse<Preview>(r));
 }catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function approve(){if(!preview)return;if(!questions.length&&advanced===null){setError('No questions to approve. Upload a file containing valid questions.');return;}setBusy(true);setError('');try{
  const document:Document=advanced===null?{schema_version:'1.0',questions}:JSON.parse(advanced);
  const r=await fetch(`/api/v1/organizations/${org}/imports/${method==='structured'?'structured/':''}${preview.id}/review`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({document,acknowledge_unresolved:acknowledged})});
  install(await readApiResponse<Preview>(r));setMessage('Faculty review saved. You can now import the approved questions.');
 }catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function keepValidRows(){
  if(!preview)return;
  const valid=questions.filter((_,i)=>!preview.errors.some(e=>e.row===i+1));
  if(!valid.length){setError('No valid questions remain. Correct the file and upload it again.');return;}
  setBusy(true);setError('');setMessage('');
  try{
   const r=await fetch(`/api/v1/organizations/${org}/imports/structured/${preview.id}/review`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({document:{schema_version:'1.0',questions:valid},acknowledge_unresolved:true})});
   install(await readApiResponse<Preview>(r));
   setMessage(`${valid.length} valid questions ready. Invalid or unmatched content was excluded. Select Import into ${presentationId?'this quiz':'question bank'} to finish.`);
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 async function suggest(index:number){if(!preview||method!=='ai')return;setBusy(true);setError('');try{
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
 return <section className="panel question-importer">
 <div className="import-heading"><div><span className="eyebrow">DOCUMENT WORKSPACE</span><h2>Import questions from a file</h2><p>Turn your teaching material into a quiz, one reviewed question at a time.</p></div><span className="import-format-badge">PDF / PPT / DOC / XLS</span></div>
 <div className="import-workspace"><div className="import-setup">
 <div className="import-section-heading"><span className="import-step">01</span><div><h3>Set up your import</h3><p>Choose a method and upload your document.</p></div></div>
 <details className="import-dropdown" open><summary>Import method <span>{method==='ai'?'AI Smart Import':'Structured Import'}</span></summary>
 <fieldset disabled={busy}><legend>Choose import method</legend><label><input type="radio" name={`import-method-${org}-${presentationId||'bank'}`} checked={method==='ai'} onChange={()=>chooseMethod('ai')}/>AI Smart Import</label><label><input type="radio" name={`import-method-${org}-${presentationId||'bank'}`} checked={method==='structured'} onChange={()=>chooseMethod('structured')}/>Structured Import (No AI API)</label></fieldset>
 </details><details className="import-dropdown" open><summary>Upload document <span>Up to 40 MB</span></summary><div className="import-upload-content">
 {method==='structured'&&<><p>Use the predefined question format. OCR runs automatically when needed. Review OCR text and answers before approval.</p><label>File type<select disabled={busy} value={fileType} onChange={e=>{setFileType(e.target.value);setSelectedFile(null);}}><option value="pdf">PDF</option><option value="pptx">PPT / PPTX</option><option value="xlsx">Excel (XLS / XLSX)</option></select></label><p><a href={`/api/v1/organizations/${org}/imports/structured/template/${fileType}`} download>Download sample template</a></p><p>One question per slide or spreadsheet row. PDF questions can start with 1., 2., or Question 1:. Separators are optional. Use A?D options and an Answer: line with the letter or option text. Explanations may follow on the next line. All four options and an explicit correct answer are required. Scanned content requires server Tesseract; legacy PPT requires server LibreOffice.</p><label>Upload structured file<input key={fileType} type="file" accept={fileType==='pdf'?'.pdf':fileType==='pptx'?'.ppt,.pptx':'.xls,.xlsx'} disabled={busy} onChange={e=>setSelectedFile(e.target.files?.[0]||null)}/></label><button type="button" disabled={busy||!selectedFile} onClick={()=>{if(selectedFile)void upload(selectedFile);}}>Extract and validate questions</button></>}
 {method==='ai'&&<><p>PDF, DOCX, PPTX, XLSX, CSV, TXT or JSON | maximum 40 MB.</p>
 <details><summary>Supported formats and answer review</summary><p>Upload the original document. PowerPoint extraction reads text boxes, groups, tables, speaker notes and slide order. Gemini can interpret difficult layouts and embedded images; full slide rendering uses the configured rendering service.</p><p>Missing answers stay blank for faculty review. AI answer suggestions are a separate, unverified action. Older DOC, PPT and XLS files require the configured conversion service or an exported DOCX, PPTX, XLSX or PDF.</p><p>Spreadsheets can use question/title, type/kind, options separated by | or individual option columns, and optional correct_answers. JSON uses schema_version 1.0 and type-specific questions. Plain text and documents may contain numbered questions and separate answer keys.</p></details>
 <label>Choose question file<input type="file" accept=".pdf,.docx,.pptx,.xlsx,.csv,.txt,.json,.doc,.ppt,.xls,.odt,.odp,.rtf" disabled={busy} onChange={e=>{const f=e.target.files?.[0];if(f){setSelectedFile(f);void upload(f);}e.target.value='';}}/></label>
 </>}
 </div></details>
 {selectedFile&&<div className="import-file"><span className="import-file-icon" aria-hidden="true">&#8593;</span><div><strong>{selectedFile.name}</strong><small>{(selectedFile.size/1000000).toFixed(2)} MB | {method==='ai'?'AI Smart Import':'Structured Import'}</small></div></div>}
 <div className="import-tip"><strong>You stay in control</strong><p>Check the extracted text and answer keys, save faculty approval, then add the questions to your quiz.</p></div>
 </div><div className="import-review" aria-label="Question review" aria-busy={busy}>
 <div className="import-section-heading"><span className="import-step">02</span><div><h3>Review &amp; finish</h3><p>Your extracted questions appear here.</p></div><span className="import-format-badge">{preview?`${questions.length} questions`:'Awaiting file'}</span></div>
 {busy&&<ProcessingIndicator>Processing your document</ProcessingIndicator>}{error&&<p role="alert" className="error">{error}</p>}{message&&<p role="status">{message}</p>}
 {!preview&&!busy&&<div className="import-empty"><div className="import-document-art" aria-hidden="true"><span>Q</span><i/><i/><i/></div><h3>From document to questions</h3><p>Upload a file on the left to preview and edit your questions here.</p><div className="import-empty-steps"><span>1. Upload</span><span>2. Review</span><span>3. Import</span></div></div>}
 {preview&&<div className="import-results"><h3>Review extracted questions</h3><p>{questions.length} questions | {preview.review_count} require review | {preview.errors.length} extraction issues{preview.detected_format?` | detected ${preview.detected_format.toUpperCase()}`:''}.</p>
 {preview.errors.map((e,i)=><p className="error" key={i}>{e.row?`Question/row ${e.row}: `:''}{e.message}</p>)}
 {method==='structured'&&<><div style={{overflowX:'auto'}}><table><thead><tr>{['Question','Option A','Option B','Option C','Option D','Correct Answer','Explanation','Validation Status'].map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>{questions.map((q,i)=><tr key={i}><td>{q.question}</td>{['A','B','C','D'].map(id=><td key={id}>{q.options?.find(o=>o.id===id)?.text}</td>)}<td>{q.correct_answers?.join(', ')||'Missing'}</td><td>{q.explanation}</td><td>{dirty?'Revalidate on approval':preview.errors.some(e=>e.row===i+1)?'Invalid | see errors':q.requires_review?'Manual review required':'Valid'}</td></tr>)}</tbody></table></div><button type="button" disabled={busy||dirty||!questions.length} onClick={()=>void keepValidRows()}>Keep valid rows only</button><p>Keep valid rows only excludes rows with validation errors and validates the remaining questions for import. If you edit questions afterward, save faculty approval again.</p></>}
 {!questions.length&&<p role="status">No editable questions were extracted. Check the source format, choose Structured Import for a template file, and upload the corrected file.</p>}

 <ol className="import-question-list">{questions.map((q,i)=><li key={i}><details className="import-question-card" open={i===0}><summary><span className="import-question-number">{String(i+1).padStart(2,'0')}</span><span className="import-question-title">{q.question||'Untitled question'}<small>{q.type.replaceAll('_',' ')} | {q.requires_review?'Faculty review required':'Ready for review'}</small></span></summary><fieldset disabled={busy}><legend>Question {i+1}{q.requires_review?' | Faculty review required':''}</legend>
 <p>{q.source?.filename}{q.source?.slide_number?` | Slide ${q.source.slide_number}`:q.source?.page_number?` | Page ${q.source.page_number}`:q.source?.row_number?` | Row ${q.source.row_number}`:''}{(q.source?.sections?.length||0)>1?` | Spans sections ${q.source!.sections!.join(', ')}`:''}</p>
 {method==='ai'&&<label>Question type<select value={q.type} onChange={e=>edit(i,changeType(q,e.target.value))}>{types.map(type=><option key={type} value={type}>{type.replaceAll('_',' ')}</option>)}</select></label>}
 {(q.body||q.source?.answer_evidence)&&<details><summary>Extracted source text / answer evidence</summary>{q.body&&<pre style={{whiteSpace:'pre-wrap'}}>{q.body}</pre>}{q.source?.answer_evidence&&<p>{q.source.answer_evidence}</p>}</details>}
 <label>Question<textarea maxLength={500} value={q.question} onChange={e=>edit(i,{question:e.target.value})}/></label>
 {q.options?.map((o,j)=><div key={o.id}><label>{o.id}<input maxLength={300} value={o.text} onChange={e=>edit(i,{options:q.options!.map((v,k)=>j===k?{...v,text:e.target.value}:v)})}/></label>{scored(q.type)&&<label><input type="checkbox" checked={q.correct_answers?.includes(o.id)||false} onChange={e=>edit(i,{correct_answers:e.target.checked?q.type==='multiple_select'?[...(q.correct_answers||[]),o.id]:[o.id]:(q.correct_answers||[]).filter(a=>a!==o.id),answer_origin:'faculty'})}/>Correct answer</label>}</div>)}
 {q.type==='short_answer'&&<><label>Accepted answers (one per line; optional for an ungraded response)<textarea value={q.accepted_answers?.join('\n')||''} onChange={e=>edit(i,{accepted_answers:e.target.value.split('\n').filter(a=>a.trim()),answer_origin:'faculty'})}/></label><label>Model answer (optional)<textarea value={q.model_answer||''} onChange={e=>edit(i,{model_answer:e.target.value})}/></label></>}
 {q.answer_origin==='ai_suggested'&&<p role="status">AI-suggested answer | unverified. Faculty approval is required.</p>}
 {scored(q.type)&&!q.correct_answers?.length&&<p className="error">No explicit correct answer found. Select an answer after checking the source.</p>}
 <label>Explanation (optional)<textarea maxLength={3000} value={q.explanation||''} onChange={e=>edit(i,{explanation:e.target.value})}/></label>
 {method==='ai'&&(scored(q.type)||q.type==='short_answer')&&i<preview.rows.length&&<button type="button" className="secondary" onClick={()=>void suggest(i)}>Generate/Verify Answer with AI</button>}
 <button type="button" className="secondary" onClick={()=>{setQuestions(old=>old.filter((_,index)=>index!==i));setDirty(true);setAdvanced(null);}}>Remove question</button>
 </fieldset></details></li>)}</ol>
 <details><summary>Review canonical JSON / resolve unmatched questions</summary><p>You can correct options, ranges, source associations or add missing questions here. All questions are validated again before approval.</p><textarea aria-label="Canonical question JSON" rows={15} disabled={busy} value={advanced??JSON.stringify({schema_version:'1.0',questions},null,2)} onChange={e=>{setAdvanced(e.target.value);setDirty(true);}}/></details>
 {!!preview.errors.length&&<label><input type="checkbox" checked={acknowledged} disabled={busy} onChange={e=>setAcknowledged(e.target.checked)}/>I checked the original document and resolved or intentionally excluded the reported invalid or unmatched content. Only the questions shown will be imported.</label>}
 <div className="import-approval-actions"><button type="button" disabled={busy||(!questions.length&&advanced===null)||!!preview.errors.length&&!acknowledged} onClick={()=>void approve()}>Save faculty approval</button>
 <button disabled={busy||dirty||!preview.can_commit} onClick={()=>void commit()}>Import into {presentationId?'this quiz':'question bank'}</button>
 </div></div>}</div></div></section>;
}
