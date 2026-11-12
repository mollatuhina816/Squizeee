'use client';
import { authFetch } from '../../../auth-fetch';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import SchedulePanel from '../../../schedule-panel';
import SlideTypePicker from '../../../slide-type-picker';
import { HotspotInput } from '../../../live-formats';
import QuestionImporter from '../../../question-importer';
import AIQuestionGenerator from '../../../ai-question-generator';
import QuestionBankPicker from '../../../question-bank-picker';
import type { QuizQuestion } from '../../../quiz-question';
import { readApiResponse } from '../../../api-response';
import { cleanQuestion, renamedAnswers } from '../../../question-editing';
import { AcademicIcon } from '../../../ui-primitives';
import { useEffect, useRef, useState } from 'react';

type Question = QuizQuestion;
const fresh = ():Question => ({kind:'mcq',title:'Untitled question',body:'',options:['Option A','Option B'],correct_answers:['Option A'],explanation:'',marks:'1',negative_marks:'0',speed_bonus:'1',duration_seconds:30,minimum:1,maximum:5});
const kinds = ['mcq','multiple_select','true_false','short_answer','ranking','scale','rating','word_cloud','poll','quiz','qa','survey','nps','content','hotspot'];
export default function Editor(){
  const {org,id} = useParams<{org:string;id:string}>();
  const [questions,setQuestions]=useState<Question[]>([]);
  const [index,setIndex]=useState(0);
  const [title,setTitle]=useState('Presentation');
  const [revision,setRevision]=useState(0);
  const [duration,setDuration]=useState(30);
  const [deliveryMode,setDeliveryMode]=useState('guided');
  const [teamMode,setTeamMode]=useState(false);
  const [streaks,setStreaks]=useState(true);
  const [allowGuests,setAllowGuests]=useState(true);
  const [message,setMessage]=useState('Loading…');
  const [saveError,setSaveError]=useState('');
  const saving=useRef(false);
  const [busy,setBusy]=useState(false);
  const [dirty,setDirty]=useState(false);
  const [showSchedule,setShowSchedule]=useState(false);
  const [showImport,setShowImport]=useState(false);
  const [importBusy,setImportBusy]=useState(false);const [showPreview,setShowPreview]=useState(false);
  const question=questions[index];
  const endpoint=`/api/v1/organizations/${org}/presentations/${id}/slides`;
  useEffect(()=>{let current=true; authFetch(endpoint).then(readApiResponse<{questions:Question[];title:string;revision:number;duration_minutes:number;live_settings?:{delivery_mode?:string;team_mode?:boolean;streaks?:boolean;allow_guests?:boolean}}>).then(d=>{if(current){setQuestions(d.questions);setTitle(d.title);setRevision(d.revision);setDuration(d.duration_minutes);setDeliveryMode(d.live_settings?.delivery_mode||'guided');setTeamMode(d.live_settings?.team_mode??false);setStreaks(d.live_settings?.streaks??true);setAllowGuests(d.live_settings?.allow_guests??true);setMessage('All changes saved');}}).catch(e=>setMessage(e.message));return()=>{current=false;};},[endpoint]);
  useEffect(()=>{const warn=(e:BeforeUnloadEvent)=>{if(dirty){e.preventDefault();e.returnValue='';}};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);},[dirty]);
  function change(patch:Partial<Question>){setQuestions(old=>old.map((q,i)=>i===index?{...q,...patch}:q));setDirty(true);setMessage('Unsaved changes');}
  function add(kind:string){
    const next=fresh();
    next.kind=kind;
    next.title=kind==='content'?'Untitled slide':'Untitled question';
    next.options=kind==='true_false'?['True','False']:['mcq','multiple_select','ranking','poll','quiz'].includes(kind)?next.options:[];
    next.correct_answers=['mcq','multiple_select','true_false','quiz'].includes(kind)?[next.options[0]]:[];
    if(kind==='nps'){next.minimum=0;next.maximum=10;}
    if(kind==='hotspot'){next.image_url='';next.image_alt='';next.hotspot_target={x:.5,y:.5,radius:.12};}
    setQuestions(old=>[...old,next]);setIndex(questions.length);setDirty(true);setMessage('Unsaved changes');
  }
  function addBankQuestions(added:Question[]){const first=questions.length;setQuestions(old=>[...old,...added]);setIndex(first);setDirty(true);setMessage(`${added.length} Question Bank question${added.length===1?'':'s'} added. Save changes before presenting.`);}
  function addAIQuestions(added:Question[]){const first=questions.length;setQuestions(old=>[...old,...added]);setIndex(first);setDirty(true);setMessage(`${added.length} AI question${added.length===1?'':'s'} added. Save changes before presenting.`);}
  function reorder(delta:number){const next=index+delta;if(next<0||next>=questions.length)return;const copy=[...questions];[copy[index],copy[next]]=[copy[next],copy[index]];setQuestions(copy);setIndex(next);setDirty(true);}
  async function save():Promise<number|null>{
    if(saving.current)return null;
    saving.current=true;setBusy(true);setSaveError('');setMessage('Saving changes…');
    try{
      const cleaned=questions.map(cleanQuestion);
      const r=await authFetch(endpoint,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision,questions:cleaned,duration_minutes:duration,live_settings:{delivery_mode:deliveryMode,team_mode:teamMode,streaks,allow_guests:allowGuests}})});
      const d=await readApiResponse<{revision:number}>(r);
      setRevision(d.revision);setQuestions(cleaned);setDirty(false);setMessage('All changes saved');return d.revision;
    }catch(e){const text=(e as Error).message;setMessage('Changes have not been saved');setSaveError(text);const match=text.match(/Question (\d+):/);if(match)setIndex(Number(match[1])-1);return null;}
    finally{saving.current=false;setBusy(false);}
  }
  async function addToBank():Promise<boolean>{if(!question)return false;if(await save()===null)return false;setBusy(true);try{const r=await authFetch(`/api/v1/organizations/${org}/bank/questions`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:cleanQuestion(question)})});await readApiResponse(r);setMessage('Presentation saved and question added to bank');return true;}catch(e){setSaveError((e as Error).message);return false;}finally{setBusy(false);}}
  const choices=question&&['mcq','multiple_select','true_false','ranking','poll','quiz'].includes(question.kind);
  return <div className="editor"><header><Link href="/" onClick={e=>{if(dirty&&!window.confirm('Leave without saving?'))e.preventDefault();}}>← Workspace</Link><strong>{title}</strong><div className="actions"><AIQuestionGenerator org={org} disabled={busy||importBusy||!revision} onAddToPresentation={addAIQuestions}/><button className="secondary" disabled={busy||importBusy||!revision} onClick={()=>setShowImport(x=>!x)}>Import PDF / PowerPoint</button><button className="secondary" disabled={busy||importBusy||!revision} onClick={()=>setShowSchedule(x=>!x)}>Schedule quiz</button><button className="secondary" disabled={busy||importBusy||dirty||!questions.length} onClick={async()=>{setBusy(true);try{const r=await authFetch(`/api/v1/organizations/${org}/presentations/${id}/sessions`,{method:"POST",headers:{'Content-Type':'application/json'},body:JSON.stringify({delivery_mode:deliveryMode,team_mode:teamMode,streaks,allow_guests:allowGuests})});const d=await r.json();if(!r.ok)throw Error(d.detail);location.href=`/live/${d.id}`;}catch(e){setMessage((e as Error).message);setBusy(false);}}}>Present</button><button disabled={busy||importBusy||!revision} onClick={save}>{busy?'Saving…':'Save changes'}</button></div></header>
    {saveError&&<p className="error" role="alert">{saveError} Your edits are still in this editor.</p>}
    {showImport&&<QuestionImporter<Question> org={org} presentationId={id} beforeImport={save} onBusyChange={setImportBusy} onImported={result=>{if(result.questions&&result.revision){setQuestions(result.questions);setRevision(result.revision);setDirty(false);setMessage('Imported questions saved');setSaveError('');}}}/>}
    {showSchedule&&<SchedulePanel base={`/api/v1/organizations/${org}/presentations/${id}`} save={save}/>}
    <fieldset className="editor-layout" disabled={busy||importBusy} style={{border:0,padding:0,margin:0,minWidth:0}}><aside><SlideTypePicker disabled={!revision} onSelect={add}/><h2>Questions <span className="count">{questions.length}</span></h2><nav aria-label="Presentation questions">{questions.map((q,i)=><button key={i} className={index===i?'active':''} aria-current={index===i?'step':undefined} onClick={()=>setIndex(i)}><span>{i+1}</span>{q.title}</button>)}</nav><QuestionBankPicker org={org} disabled={!revision} onAdd={addBankQuestions}/></aside>
    <main className="editor-canvas"><p role="status" className="editor-status">{message}</p>{question?<>{showPreview&&<><div className="actions"><button type="button" className="secondary" onClick={()=>setShowPreview(false)}>Close without saving</button><button type="button" disabled={busy} onClick={async()=>{if(await addToBank())setShowPreview(false);}}>Save to Question Bank &amp; close</button></div><div className="slide-preview"><span className="eyebrow">{question.kind.replaceAll('_',' ')} · {index+1} / {questions.length}</span><h1>{question.title}</h1>{question.body&&<p>{question.body}</p>}<div className="preview-options">{question.options.map((x,i)=><div key={i}><span>{String.fromCharCode(65+i)}</span>{x}</div>)}</div>{['scale','rating','nps'].includes(question.kind)&&<p>Scale: {question.kind==='nps'?0:question.minimum} to {question.kind==='nps'?10:question.maximum}</p>}</div></>}<div className="actions">{!showPreview&&<button type="button" className="secondary" onClick={()=>setShowPreview(true)}>Preview question</button>}<button className="secondary" onClick={()=>reorder(-1)} disabled={index===0}>Move up</button><button className="secondary" onClick={()=>reorder(1)} disabled={index===questions.length-1}>Move down</button><button className="secondary" onClick={()=>{setQuestions(old=>[...old,structuredClone(question)]);setIndex(questions.length);setDirty(true);}}>Duplicate</button><button className="secondary" onClick={()=>{if(!window.confirm('Delete this question?'))return;setQuestions(old=>old.filter((_,i)=>i!==index));setIndex(Math.max(0,index-1));setDirty(true);}}>Delete</button></div></>:<section className="empty"><span className="empty-art"><AcademicIcon/></span><h1>Start with a question</h1><p>Add a question and shape your next lesson.</p><SlideTypePicker disabled={!revision} onSelect={add}/></section>}</main>
    <div className="editor-right"><section className="panel editor-live-settings" aria-label="Live settings"><h2>Live settings</h2><div className="actions"><label>Live pacing<select value={deliveryMode} disabled={busy||importBusy||!revision} onChange={e=>{setDeliveryMode(e.target.value);setDirty(true);setMessage('Unsaved changes');}}><option value="guided">Presenter-paced</option><option value="self_paced">Self-paced</option></select></label><label><input type="checkbox" checked={teamMode} disabled={busy||importBusy||!revision} onChange={e=>{setTeamMode(e.target.checked);setDirty(true);setMessage('Unsaved changes');}}/> Team competition</label><label><input type="checkbox" checked={streaks} disabled={busy||importBusy||!revision} onChange={e=>{setStreaks(e.target.checked);setDirty(true);setMessage('Unsaved changes');}}/> Streak multipliers</label><label><input type="checkbox" checked={allowGuests} disabled={busy||importBusy||!revision} onChange={e=>{setAllowGuests(e.target.checked);setDirty(true);setMessage('Unsaved changes');}}/> Allow guests</label></div><p>Save these settings, then select Present to create a new session. Existing sessions keep the mode they started with. Correct answers earn 1.5x from a 3-answer streak and 2x from 5. Presenter-paced mode keeps everyone on the same question.</p><label>Total quiz duration<select value={duration} disabled={busy||importBusy||!revision} onChange={e=>{setDuration(Number(e.target.value));setDirty(true);setMessage('Unsaved changes');}}>{[10,15,20,30,45,60,90,120].map(n=><option key={n} value={n}>{n} minutes</option>)}</select></label><p>Applies when you assign this quiz to students. Each student's timer begins when they start; the scheduled closing time is the final deadline.</p></section></div><section className="editor-settings qs-inline" aria-label="Question settings">{question&&<><div className="qs-head"><h2>Question settings</h2><span className="qs-badge">Question {index+1}</span></div><label>Type<select value={question.kind} onChange={e=>{const kind=e.target.value;
        const options=kind==='true_false'?['True','False']:['mcq','multiple_select','ranking','poll','quiz'].includes(kind)?(question.options.length>=2?question.options:['Option A','Option B']):[];
        const valid=question.correct_answers.filter(answer=>options.includes(answer));
        const correct_answers=kind==='short_answer'?(question.kind==='short_answer'?question.correct_answers:['Answer']):kind==='multiple_select'?valid:['mcq','quiz','true_false'].includes(kind)?valid.slice(0,1):[];
        change({kind,options,correct_answers,...(kind==='hotspot'?{image_url:question.image_url||'',hotspot_target:question.hotspot_target||{x:.5,y:.5,radius:.12}}:{})});}}>{kinds.map(k=><option key={k} value={k}>{k.replaceAll('_',' ')}</option>)}</select></label>
      <label>Question<input maxLength={500} value={question.title} onChange={e=>change({title:e.target.value})}/></label><label>Supporting text<textarea value={question.body} maxLength={5000} onChange={e=>change({body:e.target.value})}/></label>
      <label>Speaker notes<textarea aria-label="Speaker notes" value={question.speaker_notes||''} maxLength={5000} onChange={e=>change({speaker_notes:e.target.value})}/></label>
      {question.kind==='hotspot'&&<><label>Image URL (HTTPS)<input type="url" value={question.image_url||''} onChange={e=>change({image_url:e.target.value})}/></label><label>Image description<input value={question.image_alt||''} maxLength={300} onChange={e=>change({image_alt:e.target.value})}/></label>{question.image_url?.startsWith('https://')&&<HotspotInput url={question.image_url} alt={question.image_alt||''} value={question.hotspot_target||null} target={question.hotspot_target||undefined} onChange={pin=>change({hotspot_target:{...pin,radius:question.hotspot_target?.radius||.12}})}/>}<label>Target radius (% of normalized image)<input type="number" min={1} max={100} value={Math.round((question.hotspot_target?.radius||.12)*100)} onChange={e=>change({hotspot_target:{x:question.hotspot_target?.x??.5,y:question.hotspot_target?.y??.5,radius:Number(e.target.value)/100}})}/></label></>}
      {question.kind==='ranking'&&<label>Correct order (one option per line; leave blank for an ungraded ranking)<textarea value={question.correct_answers.join('\n')} onChange={e=>change({correct_answers:e.target.value.split('\n')})}/></label>}
      {choices&&<label>Options (one per line)<textarea value={question.options.join('\n')} onChange={e=>{const options=e.target.value.split('\n');change({options,correct_answers:renamedAnswers(question.options,question.correct_answers,options)});}} disabled={question.kind==='true_false'}/></label>}
      {['mcq','multiple_select','true_false','short_answer','quiz','ranking','hotspot'].includes(question.kind)&&<>{['ranking','hotspot'].includes(question.kind)?null:question.kind==='short_answer'?<label>Accepted answers (one per line)<textarea value={question.correct_answers.join('\n')} onChange={e=>change({correct_answers:e.target.value.split('\n')})}/></label>:<fieldset><legend>{question.kind==='multiple_select'?'Select correct answers':'Select the correct answer'}</legend>{question.options.map((option,i)=><label key={i}><input type={question.kind==='multiple_select'?'checkbox':'radio'} name="correct-answer" checked={question.correct_answers.includes(option)} disabled={!option.trim()} onChange={e=>change({correct_answers:question.kind==='multiple_select'?(e.target.checked?[...question.correct_answers,option]:question.correct_answers.filter(x=>x!==option)):[option]})}/>{option||'Enter option text'}</label>)}</fieldset>}<label>Explanation<textarea value={question.explanation} maxLength={3000} onChange={e=>change({explanation:e.target.value})}/></label><div className="scoring-grid">{(['marks','negative_marks','speed_bonus'] as const).map(field=><label key={field}>{field.replaceAll('_',' ')}<input type="number" min="0" max="1000" step="0.001" value={question[field]} onChange={e=>change({[field]:e.target.value})}/></label>)}</div></>}
      <label>Time limit (seconds)<input type="number" min="5" max="3600" value={question.duration_seconds} onChange={e=>change({duration_seconds:Number(e.target.value)})}/></label>
      {['scale','rating'].includes(question.kind)&&<div className="scoring-grid"><label>Minimum<input type="number" value={question.minimum} onChange={e=>change({minimum:Number(e.target.value)})}/></label><label>Maximum<input type="number" value={question.maximum} onChange={e=>change({maximum:Number(e.target.value)})}/></label></div>}
      <button className="secondary" disabled={busy} onClick={()=>void addToBank()}>Save question and add to bank</button>
      <div className="qs-actions"><button type="button" disabled={busy} onClick={()=>void save()}>{busy?'Saving...':'Save'}</button></div><p className="development-note">Answers and explanations are kept in the faculty editor. Student views receive only the public question.</p></>}</section></fieldset></div>;
}

