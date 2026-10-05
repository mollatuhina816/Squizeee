'use client';
import { useParams } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
import { readApiResponse } from '../../api-response';
import ResultsPreview from '../../results-preview';

type Answer=string|string[]|null;
type Question={kind:string;title:string;body:string;options:string[]};
type Quiz={title:string;status:string;ends_at:string;score:number|null;questions?:Question[];answers?:Answer[];duration_minutes:number;started_at:string|null;deadline_at:string|null;server_now:string};
export default function QuizPage(){
  const {id}=useParams<{id:string}>();
  const [quiz,setQuiz]=useState<Quiz|null>(null);const [answers,setAnswers]=useState<Answer[]>([]);
  const [error,setError]=useState('');const [busy,setBusy]=useState(false);const [remaining,setRemaining]=useState<number|null>(null);const [saveStatus,setSaveStatus]=useState('');
  const clock=useRef({server:0,local:0,deadline:0});const latest=useRef<Answer[]>([]);const queue=useRef(Promise.resolve());const submitting=useRef(false);
  const base=`/api/v1/student/quizzes/${id}`;
  const receive=useCallback((q:Quiz,restore=false)=>{
    clock.current={server:Date.parse(q.server_now),local:performance.now(),deadline:q.deadline_at?Date.parse(q.deadline_at):0};
    setRemaining(q.deadline_at?Math.max(0,Math.ceil((Date.parse(q.deadline_at)-Date.parse(q.server_now))/1000)):null);
    setQuiz(old=>old?.status==='submitted'?old:{...old,...q});
    if(restore&&q.answers){latest.current=q.answers;setAnswers(q.answers);}
  },[]);
  const refresh=useCallback(async(restore=false)=>{const r=await fetch(base);receive(await readApiResponse<Quiz>(r),restore);},[base,receive]);
  useEffect(()=>{let active=true;fetch(base).then(readApiResponse<Quiz>).then(q=>{if(active)receive(q,true);}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[base,receive]);
  useEffect(()=>{const timer=setInterval(()=>{const c=clock.current;if(c.deadline)setRemaining(Math.max(0,Math.ceil((c.deadline-c.server-(performance.now()-c.local))/1000)));},250);return()=>clearInterval(timer);},[]);
  useEffect(()=>{if(!quiz?.started_at||quiz.status!=='open')return;const sync=()=>refresh().catch(e=>setError(e.message));const timer=setInterval(sync,10000);const visible=()=>{if(document.visibilityState==='visible')sync();};window.addEventListener('online',sync);document.addEventListener('visibilitychange',visible);return()=>{clearInterval(timer);window.removeEventListener('online',sync);document.removeEventListener('visibilitychange',visible);};},[quiz?.started_at,quiz?.status,refresh]);
  const submit=useCallback(async()=>{
    if(submitting.current)return;submitting.current=true;setBusy(true);setError('');
    try{await queue.current;const r=await fetch(`${base}/submit`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({answers:latest.current})});receive(await readApiResponse<Quiz>(r));}
    catch(e){setError((e as Error).message);await refresh().catch(()=>{});}finally{submitting.current=false;setBusy(false);}
  },[base,receive,refresh]);
  useEffect(()=>{if(remaining!==0||quiz?.status!=='open'||!quiz.started_at)return;void submit();const retry=setInterval(()=>void submit(),2000);return()=>clearInterval(retry);},[remaining,quiz?.status,quiz?.started_at,submit]);
  async function start(){setBusy(true);setError('');try{const r=await fetch(`${base}/start`,{method:'POST'});receive(await readApiResponse<Quiz>(r),true);}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  function answer(index:number,value:Answer){
    const updated=latest.current.map((x,i)=>i===index?value:x);latest.current=updated;setAnswers(updated);setSaveStatus('Saving answers...');
    queue.current=queue.current.then(async()=>{const r=await fetch(`${base}/draft`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({answers:updated}),keepalive:true});const q=await readApiResponse<Quiz>(r);receive(q);if(latest.current===updated){setSaveStatus(q.status==='submitted'?'Submitted':'Answers saved');setError('');}}).catch(e=>{setSaveStatus('Answers not saved. Check your connection and retry.');setError((e as Error).message);});
  }
  const expired=remaining===0;const active=quiz?.status==='open'&&!!quiz.started_at;
  return <main className="live-content"><a href="/student">Go to Dashboard</a><h1>{quiz?.title||'Assigned quiz'}</h1>
    {active&&<div className={`quiz-timer ${remaining!==null&&remaining<=60?'quiz-timer-urgent':''}`}><span>Time remaining</span><strong role="timer" aria-label="Time remaining">{String(Math.floor((remaining||0)/60)).padStart(2,'0')}:{String((remaining||0)%60).padStart(2,'0')}</strong><span>{expired?'Time is up. Submitting your saved answers...':'Your quiz submits automatically when time runs out.'}</span></div>}
    {error&&<p role="alert" className="error">{error}</p>}
    {quiz?.status==='submitted'?<><p role="status">Submitted. Your score: {(quiz.score||0)/1000} marks.</p><a className="dashboard-link" href="/student">Go to Dashboard</a><ResultsPreview url={`${base}/results`}/></>:quiz?.status==='open'&&!quiz.started_at?<section className="panel"><h2>Ready to start?</h2><p>You have up to {quiz.duration_minutes} minutes from when you start. The quiz closes at {new Date(quiz.ends_at).toLocaleString()}, even if your timer has time remaining.</p><p>Unanswered questions receive zero marks. Refreshing or leaving this page does not pause the timer.</p><button disabled={busy} onClick={start}>{busy?'Starting...':'Start quiz'}</button></section>:active?<><p role="status">{saveStatus}</p>{saveStatus.startsWith('Answers not saved')&&<button onClick={()=>answer(0,latest.current[0])}>Retry saving answers</button>}<fieldset disabled={busy||expired} style={{border:0,padding:0}}>{quiz.questions?.map((q,i)=><section className="panel" key={i}><h2>{i+1}. {q.title}</h2><p>{q.body}</p>{q.kind==='short_answer'?<label>Your answer<input value={String(answers[i]||'')} onChange={e=>answer(i,e.target.value)}/></label>:<div className="answer-options">{q.options.map(option=><label key={option}><input type={q.kind==='multiple_select'?'checkbox':'radio'} name={`question-${i}`} checked={q.kind==='multiple_select'?((answers[i] as string[])||[]).includes(option):answers[i]===option} onChange={e=>answer(i,q.kind==='multiple_select'?(e.target.checked?[...((answers[i] as string[])||[]),option]:((answers[i] as string[])||[]).filter(x=>x!==option)):option)}/>{option}</label>)}</div>}</section>)}<button onClick={()=>void submit()}>{busy?'Submitting...':'Submit quiz'}</button></fieldset></>:quiz?<p>This quiz is {quiz.status}. Return to your dashboard to check its schedule.</p>:<p>Loading quiz...</p>}
  </main>;
}
