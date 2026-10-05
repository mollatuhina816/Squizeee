'use client';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import SchedulePanel from '../../../schedule-panel';
import QuestionImporter from '../../../question-importer';
import AIQuestionGenerator from '../../../ai-question-generator';
import QuestionBankPicker from '../../../question-bank-picker';
import type { QuizQuestion } from '../../../quiz-question';
import { readApiResponse } from '../../../api-response';
import { cleanQuestion, renamedAnswers } from '../../../question-editing';
import { useEffect, useRef, useState } from 'react';

type Question = QuizQuestion;
const fresh = ():Question => ({kind:'mcq',title:'Untitled question',body:'',options:['Option A','Option B'],correct_answers:['Option A'],explanation:'',marks:'1',negative_marks:'0',speed_bonus:'0',duration_seconds:30,minimum:1,maximum:5});
const kinds = ['mcq','multiple_select','true_false','short_answer','ranking','scale','rating','word_cloud','poll','quiz','qa','survey','nps','content'];
export default function Editor(){
  const {org,id} = useParams<{org:string;id:string}>();
  const [questions,setQuestions]=useState<Question[]>([]);
  const [index,setIndex]=useState(0);
  const [title,setTitle]=useState('Presentation');
  const [revision,setRevision]=useState(0);
  const [duration,setDuration]=useState(30);
  const [message,setMessage]=useState('Loading…');
  const [saveError,setSaveError]=useState('');
  const saving=useRef(false);
  const [busy,setBusy]=useState(false);
  const [dirty,setDirty]=useState(false);
  const [showSchedule,setShowSchedule]=useState(false);
  const [showImport,setShowImport]=useState(false);
  const [importBusy,setImportBusy]=useState(false);
  const question=questions[index];
  const endpoint=`/api/v1/organizations/${org}/presentations/${id}/slides`;
  useEffect(()=>{let current=true; fetch(endpoint).then(readApiResponse<{questions:Question[];title:string;revision:number;duration_minutes:number}>).then(d=>{if(current){setQuestions(d.questions);setTitle(d.title);setRevision(d.revision);setDuration(d.duration_minutes);setMessage('All changes saved');}}).catch(e=>setMessage(e.message));return()=>{current=false;};},[endpoint]);
  useEffect(()=>{const warn=(e:BeforeUnloadEvent)=>{if(dirty){e.preventDefault();e.returnValue='';}};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);},[dirty]);
  function change(patch:Partial<Question>){setQuestions(old=>old.map((q,i)=>i===index?{...q,...patch}:q));setDirty(true);setMessage('Unsaved changes');}
  function add(){setQuestions(old=>[...old,fresh()]);setIndex(questions.length);setDirty(true);setMessage('Unsaved changes');}
  function addBankQuestions(added:Question[]){const first=questions.length;setQuestions(old=>[...old,...added]);setIndex(first);setDirty(true);setMessage(`${added.length} Question Bank question${added.length===1?'':'s'} added. Save changes before presenting.`);}
  function addAIQuestions(added:Question[]){const first=questions.length;setQuestions(old=>[...old,...added]);setIndex(first);setDirty(true);setMessage(`${added.length} AI question${added.length===1?'':'s'} added. Save changes before presenting.`);}
  function reorder(delta:number){const next=index+delta;if(next<0||next>=questions.length)return;const copy=[...questions];[copy[index],copy[next]]=[copy[next],copy[index]];setQuestions(copy);setIndex(next);setDirty(true);}
  async function save():Promise<number|null>{
    if(saving.current)return null;
    saving.current=true;setBusy(true);setSaveError('');setMessage('Saving changes?');
    try{
      const cleaned=questions.map(cleanQuestion);
      const r=await fetch(endpoint,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision,questions:cleaned,duration_minutes:duration})});
      const d=await readApiResponse<{revision:number}>(r);
      setRevision(d.revision);setQuestions(cleaned);setDirty(false);setMessage('All changes saved');return d.revision;
    }catch(e){const text=(e as Error).message;setMessage('Changes have not been saved');setSaveError(text);const match=text.match(/Question (\d+):/);if(match)setIndex(Number(match[1])-1);return null;}
    finally{saving.current=false;setBusy(false);}
  }
  const choices=question&&['mcq','multiple_select','true_false','ranking','poll','quiz'].includes(question.kind);
  return <div className="editor"><header><Link href="/" onClick={e=>{if(dirty&&!window.confirm('Leave without saving?'))e.preventDefault();}}>← Workspace</Link><strong>{title}</strong><div className="actions"><AIQuestionGenerator org={org} disabled={busy||importBusy||!revision} onAddToPresentation={addAIQuestions}/><button className="secondary" disabled={busy||importBusy||!revision} onClick={()=>setShowImport(x=>!x)}>Import PDF / PowerPoint</button><button className="secondary" disabled={busy||importBusy||!revision} onClick={()=>setShowSchedule(x=>!x)}>Schedule quiz</button><button className="secondary" disabled={busy||importBusy||dirty||!questions.length} onClick={async()=>{setBusy(true);try{const r=await fetch(`/api/v1/organizations/${org}/presentations/${id}/sessions`,{method:"POST"});const d=await r.json();if(!r.ok)throw Error(d.detail);location.href=`/live/${d.id}`;}catch(e){setMessage((e as Error).message);setBusy(false);}}}>Present</button><button disabled={busy||importBusy||!revision} onClick={save}>{busy?'Saving…':'Save changes'}</button></div></header>
    <section className="panel"><label>Total quiz duration<select value={duration} disabled={busy||importBusy||!revision} onChange={e=>{setDuration(Number(e.target.value));setDirty(true);setMessage('Unsaved changes');}}>{[10,15,20,30,45,60,90,120].map(n=><option key={n} value={n}>{n} minutes</option>)}</select></label><p>Applies when you assign this quiz to students. Each student's timer begins when they start; the scheduled closing time is the final deadline.</p></section>
    {saveError&&<p className="error" role="alert">{saveError} Your edits are still in this editor.</p>}
    {showImport&&<QuestionImporter<Question> org={org} presentationId={id} beforeImport={save} onBusyChange={setImportBusy} onImported={result=>{if(result.questions&&result.revision){setQuestions(result.questions);setRevision(result.revision);setDirty(false);setMessage('Imported questions saved');setSaveError('');}}}/>}
    {showSchedule&&<SchedulePanel base={`/api/v1/organizations/${org}/presentations/${id}`} save={save}/>}
    <fieldset className="editor-layout" disabled={busy||importBusy} style={{border:0,padding:0,margin:0,minWidth:0}}><aside><h2>Questions <span className="count">{questions.length}</span></h2><nav>{questions.map((q,i)=><button key={i} className={index===i?'active':''} onClick={()=>setIndex(i)}><span>{i+1}</span>{q.title}</button>)}</nav><button onClick={add} disabled={!revision}>＋ Add question</button><QuestionBankPicker org={org} disabled={!revision} onAdd={addBankQuestions}/></aside>
    <main className="editor-canvas"><p role="status" className="editor-status">{message}</p>{question?<><div className="slide-preview"><span className="eyebrow">{question.kind.replaceAll('_',' ')} · {index+1} / {questions.length}</span><h1>{question.title}</h1>{question.body&&<p>{question.body}</p>}<div className="preview-options">{question.options.map((x,i)=><div key={i}><span>{String.fromCharCode(65+i)}</span>{x}</div>)}</div>{['scale','rating','nps'].includes(question.kind)&&<p>Scale: {question.kind==='nps'?0:question.minimum} to {question.kind==='nps'?10:question.maximum}</p>}</div><div className="actions"><button className="secondary" onClick={()=>reorder(-1)} disabled={index===0}>Move up</button><button className="secondary" onClick={()=>reorder(1)} disabled={index===questions.length-1}>Move down</button><button className="secondary" onClick={()=>{setQuestions(old=>[...old,structuredClone(question)]);setIndex(questions.length);setDirty(true);}}>Duplicate</button><button className="secondary" onClick={()=>{if(!window.confirm('Delete this question?'))return;setQuestions(old=>old.filter((_,i)=>i!==index));setIndex(Math.max(0,index-1));setDirty(true);}}>Delete</button></div></>:<section className="empty"><h1>Start with a question</h1><p>Add a question and shape your next lesson.</p><button onClick={add} disabled={!revision}>Add question</button></section>}</main>
    <section className="editor-settings" aria-label="Question settings">{question&&<><h2>Question settings</h2><label>Type<select value={question.kind} onChange={e=>{const kind=e.target.value;
        const options=kind==='true_false'?['True','False']:['mcq','multiple_select','ranking','poll','quiz'].includes(kind)?(question.options.length>=2?question.options:['Option A','Option B']):[];
        const valid=question.correct_answers.filter(answer=>options.includes(answer));
        const correct_answers=kind==='short_answer'?(question.kind==='short_answer'?question.correct_answers:['Answer']):kind==='multiple_select'?valid:['mcq','quiz','true_false'].includes(kind)?valid.slice(0,1):[];
        change({kind,options,correct_answers});}}>{kinds.map(k=><option key={k} value={k}>{k.replaceAll('_',' ')}</option>)}</select></label>
      <label>Question<input maxLength={500} value={question.title} onChange={e=>change({title:e.target.value})}/></label><label>Supporting text<textarea value={question.body} maxLength={5000} onChange={e=>change({body:e.target.value})}/></label>
      {choices&&<label>Options (one per line)<textarea value={question.options.join('\n')} onChange={e=>{const options=e.target.value.split('\n');change({options,correct_answers:renamedAnswers(question.options,question.correct_answers,options)});}} disabled={question.kind==='true_false'}/></label>}
      {['mcq','multiple_select','true_false','short_answer','quiz'].includes(question.kind)&&<>{question.kind==='short_answer'?<label>Accepted answers (one per line)<textarea value={question.correct_answers.join('\n')} onChange={e=>change({correct_answers:e.target.value.split('\n')})}/></label>:<fieldset><legend>{question.kind==='multiple_select'?'Select correct answers':'Select the correct answer'}</legend>{question.options.map((option,i)=><label key={i}><input type={question.kind==='multiple_select'?'checkbox':'radio'} name="correct-answer" checked={question.correct_answers.includes(option)} disabled={!option.trim()} onChange={e=>change({correct_answers:question.kind==='multiple_select'?(e.target.checked?[...question.correct_answers,option]:question.correct_answers.filter(x=>x!==option)):[option]})}/>{option||'Enter option text'}</label>)}</fieldset>}<label>Explanation<textarea value={question.explanation} maxLength={3000} onChange={e=>change({explanation:e.target.value})}/></label><div className="scoring-grid">{(['marks','negative_marks','speed_bonus'] as const).map(field=><label key={field}>{field.replaceAll('_',' ')}<input type="number" min="0" max="1000" step="0.001" value={question[field]} onChange={e=>change({[field]:e.target.value})}/></label>)}</div></>}
      <label>Time limit (seconds)<input type="number" min="5" max="3600" value={question.duration_seconds} onChange={e=>change({duration_seconds:Number(e.target.value)})}/></label>
      {['scale','rating'].includes(question.kind)&&<div className="scoring-grid"><label>Minimum<input type="number" value={question.minimum} onChange={e=>change({minimum:Number(e.target.value)})}/></label><label>Maximum<input type="number" value={question.maximum} onChange={e=>change({maximum:Number(e.target.value)})}/></label></div>}
      <button className="secondary" disabled={busy} onClick={async()=>{
        if(await save()===null)return;
        setBusy(true);try{const r=await fetch(`/api/v1/organizations/${org}/bank/questions`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:cleanQuestion(question)})});await readApiResponse(r);setMessage('Presentation saved and question added to bank');}catch(e){setSaveError((e as Error).message);}finally{setBusy(false);}
      }}>Save question and add to bank</button>
      <p className="development-note">Answers and explanations are kept in the faculty editor. Student views receive only the public question.</p></>}</section></fieldset></div>;
}

