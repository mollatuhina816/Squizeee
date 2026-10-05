'use client';
import { FormEvent, useEffect, useState } from 'react';
import { readApiResponse } from '../api-response';

type Thresholds = {gold:number;platinum:number;diamond:number};
export default function AchievementSettings() {
  const [values,setValues] = useState<Thresholds|null>(null);
  const [error,setError] = useState('');
  const [saved,setSaved] = useState('');
  const [busy,setBusy] = useState(false);
  useEffect(()=>{let active=true;fetch('/api/v1/admin/achievement-settings').then(readApiResponse<Thresholds>).then(data=>{if(active)setValues(data);}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[]);
  async function save(event:FormEvent<HTMLFormElement>) {
    event.preventDefault();setBusy(true);setSaved('');setError('');
    try {const response=await fetch('/api/v1/admin/achievement-settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(values)});setValues(await readApiResponse<Thresholds>(response));setSaved('Saved. Student achievements now use these thresholds.');}
    catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  return <section className="panel achievement-settings"><h2>Student achievements</h2><p>Set the number of completed quizzes required for each level. These settings apply to all students, including existing results.</p>
    {error&&<p role="alert" className="error">{error}</p>}{saved&&<p role="status">{saved}</p>}
    {values?<form onSubmit={save}><div className="achievement-settings-fields">{(['gold','platinum','diamond'] as const).map(level=><label key={level}>{level[0].toUpperCase()+level.slice(1)}<input aria-label={`${level} completed quizzes`} type="number" min={1} max={100000} step={1} required value={values[level]} onChange={event=>{setValues({...values,[level]:Number(event.target.value)});setSaved('');}}/></label>)}</div><small>Use increasing thresholds: Gold &lt; Platinum &lt; Diamond. Points do not change when thresholds change.</small><button disabled={busy}>{busy?'Saving…':'Save achievement thresholds'}</button></form>:!error&&<p>Loading thresholds…</p>}
  </section>;
}
