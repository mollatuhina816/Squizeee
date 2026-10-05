'use client';
import { useEffect, useState } from 'react';
import { readApiResponse } from './api-response';

type Quiz={id:string;title:string;starts_at:string;ends_at:string;status:string;question_count:number};
type Attempt={id:string;source:string;quiz_id?:string;title:string;date:string;score:number;total_marks:number;percentage:number|null;status:string;points:number};
type Profile={name:string;email:string;account:boolean;total_attempted:number;completed_quizzes:number;total_points:number;average_score:number|null;highest_score:number|null;lowest_score:number|null;performance:string;achievement:string|null;next_achievement:{name:string;threshold:number;remaining:number}|null;thresholds:{gold:number;platinum:number;diamond:number};history:Attempt[]};
const percent=(value:number|null)=>value===null?'\u2014':`${value}%`;
const icon=(name:string|null)=>name==='Gold'?'\u{1F947}':name?'\u{1F48E}':'\u2606';

export default function StudentDashboard(){
  const [profile,setProfile]=useState<Profile|null>(null);
  const [quizzes,setQuizzes]=useState<Quiz[]>([]);
  const [error,setError]=useState('');const [loading,setLoading]=useState(true);const [page,setPage]=useState(0);
  useEffect(()=>{
    let active=true;let pending=false;
    async function refresh(){
      if(pending)return;pending=true;
      try{
        const data=await fetch('/api/v1/student/profile',{cache:'no-store'}).then(readApiResponse<Profile>);
        const assigned=data.account?await fetch('/api/v1/student/quizzes').then(readApiResponse<Quiz[]>):[];
        if(active){setProfile(data);setQuizzes(assigned);setError('');}
      }catch(e){if(active){setProfile(null);setQuizzes([]);setError((e as Error).message);}}
      finally{pending=false;if(active)setLoading(false);}
    }
    void refresh();const timer=setInterval(refresh,15000);window.addEventListener('focus',refresh);
    return()=>{active=false;clearInterval(timer);window.removeEventListener('focus',refresh);};
  },[]);
  if(loading)return <p role="status">Loading your student profile...</p>;
  if(!profile)return <section className="panel"><h2>Your personal dashboard</h2><p role="alert" className="error">{error}</p><a href="/">Sign in or create a student account</a><p>Use the same email you entered for your quizzes.</p></section>;
  const next=profile.next_achievement;const pages=Math.max(1,Math.ceil(profile.history.length/20));const currentPage=Math.min(page,pages-1);
  const available=quizzes.filter(q=>q.status!=='submitted');
  return <div className="student-profile">
    <section className="panel student-profile-heading"><div><span className="eyebrow">STUDENT PROFILE</span><h2>{profile.name}</h2><p>{profile.email}</p><span className="badge">{profile.performance}</span></div><div className={`achievement-emblem achievement-${(profile.achievement||'starter').toLowerCase()}`}><span aria-hidden="true">{icon(profile.achievement)}</span><strong>{profile.achievement||'Getting started'}</strong><small>Current achievement</small></div></section>
    <section aria-labelledby="performance-summary"><h2 id="performance-summary">Performance summary</h2><div className="student-stats">{[['Quizzes attempted',profile.total_attempted],['Total points',profile.total_points],['Average score',percent(profile.average_score)],['Highest score',percent(profile.highest_score)],['Lowest score',percent(profile.lowest_score)],['Completed quizzes',profile.completed_quizzes]].map(([label,value])=><article className="panel" key={label}><span>{label}</span><strong>{value}</strong></article>)}</div><p className="student-help">Each completed quiz earns its percentage rounded to whole points (0-100). Scores include speed bonuses and negative marks; percentages use the maximum available marks. Ungraded quizzes earn no points and are excluded from averages.</p></section>
    <section className="panel achievement-progress" aria-labelledby="achievement-heading"><h2 id="achievement-heading">Your achievement journey</h2>{next?<><div className="achievement-progress-label"><strong>{profile.completed_quizzes} / {next.threshold} quizzes completed</strong><span>Next: {next.name}</span></div><progress aria-label={`Progress toward ${next.name}`} max={next.threshold} value={profile.completed_quizzes}/><p>{next.remaining} more {next.remaining===1?'quiz':'quizzes'} to reach {next.name}</p></>:<p>You reached Diamond, the highest achievement. Keep building your points!</p>}<div className="achievement-levels">{Object.entries(profile.thresholds).map(([name,threshold])=><div className={profile.completed_quizzes>=threshold?'earned':''} key={name}><span aria-hidden="true">{icon(name[0].toUpperCase()+name.slice(1))}</span><strong>{name[0].toUpperCase()+name.slice(1)}</strong><small>{threshold}+ completed quizzes</small></div>)}</div></section>
    <section aria-labelledby="quiz-history"><h2 id="quiz-history">Quiz history</h2>{!profile.history.length?<div className="panel"><p>Your quiz history will appear here after you start your first quiz.</p><a href="/join">Join a quiz</a></div>:<><div className="table-wrap student-history"><table><caption className="student-help">Your individual results across live and assigned quizzes</caption><thead><tr>{['Quiz','Date','Score','Total marks','Percentage','Points','Status'].map(label=><th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{profile.history.slice(currentPage*20,(currentPage+1)*20).map(row=><tr key={`${row.source}-${row.id}`}><td>{row.source==='scheduled'?<a href={`/quiz/${row.quiz_id}`}>{row.title}</a>:row.title}<small className="student-quiz-type">{row.source==='live'?'Live quiz':'Assigned quiz'}</small></td><td>{new Date(row.date).toLocaleString()}</td><td>{row.status==='Completed'?`${row.score} / ${row.total_marks}`:'Pending'}</td><td>{row.total_marks}</td><td>{row.status==='Completed'?percent(row.percentage):'\u2014'}</td><td>{row.points}</td><td><span className="badge">{row.status}</span></td></tr>)}</tbody></table></div>{pages>1&&<div className="admin-pagination"><span>Page {currentPage+1} of {pages}</span><div><button className="secondary" disabled={!currentPage} onClick={()=>setPage(currentPage-1)}>Previous</button><button className="secondary" disabled={currentPage+1>=pages} onClick={()=>setPage(currentPage+1)}>Next</button></div></div>}</>}</section>
    {profile.account&&<section><h2>Assigned quizzes</h2>{!available.length&&<p>No pending quizzes. Your completed quizzes are in your history above.</p>}{available.map(q=><article className="panel" key={q.id}><h3>{q.title}</h3><p>{q.question_count} questions | {q.status}</p><p>{new Date(q.starts_at).toLocaleString()} - {new Date(q.ends_at).toLocaleString()}</p>{q.status==='open'&&<a href={`/quiz/${q.id}`}>Open quiz</a>}</article>)}</section>}
  </div>;
}
