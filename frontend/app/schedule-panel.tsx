'use client';
import { FormEvent, useEffect, useState } from 'react';
import { readApiResponse } from './api-response';
type Scheduled = {id:string; starts_at:string; ends_at:string; students:{email:string; submitted_at:string|null; score:number|null}[]};
export default function SchedulePanel({base, save}: {base:string; save:()=>Promise<number|null>}) {
  const [schedules,setSchedules]=useState<Scheduled[]>([]);
  const [message,setMessage]=useState('');
  const [busy,setBusy]=useState(false);
  async function refresh(){const r=await fetch(`${base}/schedules`);setSchedules(await readApiResponse<Scheduled[]>(r));}
  useEffect(()=>{refresh().catch(e=>setMessage(e.message));},[base]);
  async function schedule(event:FormEvent<HTMLFormElement>){
    event.preventDefault();const form=event.currentTarget;const values=new FormData(form);setBusy(true);setMessage('');
    try {
      const revision=await save();
      if(revision===null)throw Error('Questions could not be saved. Correct the editor error before scheduling.');
      const starts_at=new Date(String(values.get('starts_at'))).toISOString();
      const ends_at=new Date(String(values.get('ends_at'))).toISOString();
      const students=String(values.get('students')).split(/[\s,;]+/).filter(Boolean);
      const r=await fetch(`${base}/schedule`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision,starts_at,ends_at,students})});
      await readApiResponse(r);await refresh();form.reset();setMessage('Quiz assigned. Students will see it when they sign in with the listed email addresses.');
    }catch(e){setMessage((e as Error).message);}finally{setBusy(false);}
  }
  return <section className="panel"><h2>Schedule for students</h2><p>Students answer independently between these times. Times use your device’s timezone. Questions are saved before assigning; later edits do not change assigned quizzes.</p><form onSubmit={schedule}><fieldset disabled={busy}><label>Student email addresses<textarea name="students" required placeholder="student@example.com"/></label><label>Start time<input name="starts_at" type="datetime-local" required/></label><label>End time<input name="ends_at" type="datetime-local" required/></label><p>Use MCQ, multiple select, true/false, short answer or quiz questions. Scoring uses marks and negative marks, without speed bonuses.</p><button>{busy?'Scheduling…':'Save and assign quiz'}</button></fieldset></form>{message&&<p role="status">{message}</p>}<h3>Assigned quizzes</h3><button type="button" className="secondary" onClick={()=>refresh().catch(e=>setMessage(e.message))}>Refresh submissions</button>{schedules.map(q=><article key={q.id}><p>{new Date(q.starts_at).toLocaleString()} – {new Date(q.ends_at).toLocaleString()}</p><ul>{q.students.map(s=><li key={s.email}>{s.email}: {s.submitted_at?`Submitted · ${(s.score||0)/1000} marks`:'Not submitted'}</li>)}</ul></article>)}</section>;
}
