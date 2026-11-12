'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { loadParticipant } from './participant-storage';
import { readApiResponse } from './api-response';
import { AnimatedEmptyState, AnimatedProgressBar, LoadingSkeleton } from './ui-primitives';

type Quiz={id:string;title:string;starts_at:string;ends_at:string;status:string;question_count:number};
type Attempt={id:string;source:string;quiz_id?:string;title:string;date:string;score:number;total_marks:number;percentage:number|null;status:string;points:number};
type Profile={name:string;email:string;account:boolean;total_attempted:number;completed_quizzes:number;total_points:number;average_score:number|null;highest_score:number|null;lowest_score:number|null;performance:string;achievement:string|null;next_achievement:{name:string;threshold:number;remaining:number}|null;thresholds:{gold:number;platinum:number;diamond:number};history:Attempt[]};
const percent=(value:number|null)=>value===null?'\u2014':`${value}%`;
type Tier='starter'|'gold'|'platinum'|'diamond';
const TIER:{[k in Tier]:[string,string,string]}={starter:['#bfdbfe','#3b82f6','#1e3a8a'],gold:['#fde68a','#f59e0b','#92400e'],platinum:['#f1f5f9','#94a3b8','#334155'],diamond:['#bae6fd','#38bdf8','#1d4ed8']};
function TierBadge({tier}:{tier:Tier}){
  const [l,m,d]=TIER[tier];const id=`tb-${tier}`;
  const emblem=tier==='diamond'
    ?<g><path d="M22 27h20l5 6-15 16-15-16z" fill="#fff" opacity=".95"/><path d="M17 33h30M27 27l-3 6 8 16 8-16-3-6" stroke={m} strokeWidth="1.6" fill="none" strokeLinejoin="round"/></g>
    :tier==='platinum'
    ?<g><path d="M18 42l-2-14 9 6 7-11 7 11 9-6-2 14z" fill="#fff" opacity=".95"/><rect x="18" y="43" width="28" height="4" rx="2" fill="#fff"/><circle cx="32" cy="23" r="2.2" fill={m}/></g>
    :tier==='gold'
    ?<g><path d="M32 20l3.6 7.4 8.1 1.2-5.9 5.7 1.4 8.1L32 38.6l-7.2 3.8 1.4-8.1-5.9-5.7 8.1-1.2z" fill="#fff" opacity=".97"/></g>
    :<g><path d="M26 44l12-12M34 30l4-10 4 4-10 4" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" fill="none"/><circle cx="25" cy="45" r="2.5" fill="#fff"/><path d="M40 38l1.2 2.6 2.8.4-2 2 .5 2.8-2.5-1.3-2.5 1.3.5-2.8-2-2 2.8-.4z" fill="#fff"/></g>;
  return <svg className={`sd-tier sd-tier-${tier}`} viewBox="0 0 64 64" aria-hidden="true">
    <defs><linearGradient id={`${id}-f`} x1="0" y1="0" x2="1" y2="1"><stop stopColor={l}/><stop offset=".55" stopColor={m}/><stop offset="1" stopColor={d}/></linearGradient>
      <linearGradient id={`${id}-r`} x1="0" y1="0" x2="0" y2="1"><stop stopColor="#fff" stopOpacity=".9"/><stop offset="1" stopColor="#fff" stopOpacity="0"/></linearGradient></defs>
    <path d="M22 4h8l-4 14h-8zM34 4h8l4 14h-8z" fill={d} opacity=".85"/>
    <path className="sd-tier-shield" d="M32 10l18 7v14c0 12-8 19-18 23-10-4-18-11-18-23V17z" fill={`url(#${id}-f)`} stroke={d} strokeWidth="1.5"/>
    <path d="M32 14l14 5.5v11c0 9.5-6.2 15-14 18.4z" fill="#fff" opacity=".12"/>
    <path d="M18 19.5L32 14v6l-14 5z" fill={`url(#${id}-r)`} opacity=".55"/>
    {emblem}
    <path className="sd-tier-spark" d="M52 8l1.2 3 3 1.2-3 1.2L52 16.4l-1.2-3-3-1.2 3-1.2z" fill={l}/>
  </svg>;
}
const tierOf=(name:string|null):Tier=>{const n=(name||'').toLowerCase();return n==='gold'||n==='platinum'||n==='diamond'?n:'starter';};
const icon=(name:string|null)=><TierBadge tier={tierOf(name)}/>;

/* ---------- Presentational helpers (no data side effects) ---------- */
function useCountUp(target:number,duration=1200){
  const [value,setValue]=useState(0);
  useEffect(()=>{
    if(window.matchMedia('(prefers-reduced-motion: reduce)').matches){setValue(target);return;}
    let frame=0;const start=performance.now();
    const tick=(now:number)=>{const t=Math.min(1,(now-start)/duration);setValue(target*(1-Math.pow(1-t,3)));if(t<1)frame=requestAnimationFrame(tick);};
    frame=requestAnimationFrame(tick);return()=>cancelAnimationFrame(frame);
  },[target,duration]);
  return value;
}
function CountUp({value,suffix=''}:{value:number|null;suffix?:string}){const v=useCountUp(value??0);return <>{value===null?'\u2014':`${Math.round(v)}${suffix}`}</>;}

function Gauge({value,label}:{value:number|null;label:string}){
  const pct=Math.max(0,Math.min(100,value??0));const r=78;const arc=Math.PI*r;
  return <figure className="sd-gauge" aria-label={`${label}: ${percent(value)}`}>
    <svg viewBox="0 0 200 120" aria-hidden="true"><defs><linearGradient id="sd-gauge-g" x1="0" x2="1"><stop stopColor="#60a5fa"/><stop offset="1" stopColor="#1d4ed8"/></linearGradient></defs>
      <path d="M22 100a78 78 0 0 1 156 0" className="sd-gauge-track"/>
      <path d="M22 100a78 78 0 0 1 156 0" className="sd-gauge-fill" stroke="url(#sd-gauge-g)" style={{strokeDasharray:arc,strokeDashoffset:arc*(1-pct/100)}}/>
      {Array.from({length:11},(_,i)=>{const a=Math.PI*(1-i/10);return <line key={i} x1={100+66*Math.cos(a)} y1={100-66*Math.sin(a)} x2={100+60*Math.cos(a)} y2={100-60*Math.sin(a)} className="sd-gauge-tick"/>;})}
      <g className="sd-gauge-needle" style={{transform:`rotate(${-90+pct*1.8}deg)`}}><line x1="100" y1="100" x2="100" y2="40"/><circle cx="100" cy="100" r="6"/></g>
    </svg>
    <figcaption><strong><CountUp value={value} suffix="%"/></strong><span>{label}</span></figcaption>
  </figure>;
}

function TrendChart({points}:{points:{label:string;value:number;title:string}[]}){
  const w=640,h=240,pad={l:36,r:16,t:20,b:34};
  if(points.length<1)return <p className="sd-chart-empty">Complete a graded quiz to see your score trend.</p>;
  const iw=w-pad.l-pad.r,ih=h-pad.t-pad.b;const step=points.length>1?iw/(points.length-1):0;
  const xy=points.map((p,i)=>[pad.l+(points.length>1?i*step:iw/2),pad.t+ih*(1-p.value/100)] as const);
  const line=xy.map(([x,y],i)=>{if(!i)return `M${x} ${y}`;const [px,py]=xy[i-1];const cx=(px+x)/2;return `C${cx} ${py} ${cx} ${y} ${x} ${y}`;}).join(' ');
  const area=`${line} L${xy[xy.length-1][0]} ${pad.t+ih} L${xy[0][0]} ${pad.t+ih} Z`;
  return <svg className="sd-trend" viewBox={`0 0 ${w} ${h}`} role="img" aria-label={`Score trend across your last ${points.length} graded quizzes`}>
    <defs><linearGradient id="sd-area" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#3b82f6" stopOpacity=".35"/><stop offset="1" stopColor="#3b82f6" stopOpacity="0"/></linearGradient>
      <linearGradient id="sd-line" x1="0" x2="1"><stop stopColor="#60a5fa"/><stop offset="1" stopColor="#1d4ed8"/></linearGradient></defs>
    {[0,25,50,75,100].map(v=><g key={v}><line x1={pad.l} x2={w-pad.r} y1={pad.t+ih*(1-v/100)} y2={pad.t+ih*(1-v/100)} className="sd-gridline"/><text x={pad.l-8} y={pad.t+ih*(1-v/100)+4} className="sd-axis" textAnchor="end">{v}</text></g>)}
    <path d={area} fill="url(#sd-area)" className="sd-trend-area"/>
    <path d={line} stroke="url(#sd-line)" className="sd-trend-line" pathLength={1}/>
    {xy.map(([x,y],i)=><g key={i} className="sd-trend-dot" style={{animationDelay:`${.9+i*.06}s`}}><circle cx={x} cy={y} r="5"/><title>{`${points[i].title}: ${points[i].value}%`}</title></g>)}
    {points.map((p,i)=>(points.length<=8||i%Math.ceil(points.length/8)===0)&&<text key={i} x={xy[i][0]} y={h-10} className="sd-axis" textAnchor="middle">{p.label}</text>)}
  </svg>;
}

function Donut({segments,center,sub}:{segments:{label:string;value:number;tone:string}[];center:string|number;sub:string}){
  const total=segments.reduce((s,x)=>s+x.value,0);const r=54,c=2*Math.PI*r;let offset=0;
  return <div className="sd-donut-wrap"><svg className="sd-donut" viewBox="0 0 140 140" role="img" aria-label={segments.map(s=>`${s.label}: ${s.value}`).join(', ')}>
    <circle cx="70" cy="70" r={r} className="sd-donut-track"/>
    {total>0&&segments.map((s,i)=>{const len=c*s.value/total;const el=<circle key={s.label} cx="70" cy="70" r={r} className={`sd-donut-seg ${s.tone}`} style={{strokeDasharray:`${len} ${c-len}`,strokeDashoffset:-offset,animationDelay:`${i*.2}s`}}/>;offset+=len;return el;})}
    <text x="70" y="68" textAnchor="middle" className="sd-donut-num">{center}</text><text x="70" y="88" textAnchor="middle" className="sd-donut-sub">{sub}</text>
  </svg><ul className="sd-legend">{segments.map(s=><li key={s.label}><i className={s.tone}/>{s.label}<b>{s.value}</b></li>)}</ul></div>;
}

function Bars({rows}:{rows:{label:string;value:number;title:string}[]}){
  if(!rows.length)return <p className="sd-chart-empty">Points you earn will appear here.</p>;
  const max=Math.max(100,...rows.map(r=>r.value));
  return <div className="sd-bars" role="img" aria-label="Points earned in recent quizzes">{rows.map((r,i)=><div className="sd-bar" key={i} title={`${r.title}: ${r.value} points`}><span className="sd-bar-val">{r.value}</span><div className="sd-bar-col"><div style={{height:`${(r.value/max)*100}%`,animationDelay:`${i*.07}s`}}/></div><small>{r.label}</small></div>)}</div>;
}

function Ring({value,max,children}:{value:number;max:number;children:React.ReactNode}){
  const pct=max?Math.min(1,value/max):1;const r=46,c=2*Math.PI*r;
  return <div className="sd-ring"><svg viewBox="0 0 110 110" aria-hidden="true"><circle cx="55" cy="55" r={r} className="sd-ring-track"/><circle cx="55" cy="55" r={r} className="sd-ring-fill" style={{strokeDasharray:c,strokeDashoffset:c*(1-pct)}}/></svg><div>{children}</div></div>;
}

function Reveal({children,className='',delay=0,as:Tag='section',...rest}:{children:React.ReactNode;className?:string;delay?:number;as?:'section'|'article'|'div'}&React.HTMLAttributes<HTMLElement>){
  const ref=useRef<HTMLElement>(null);const [shown,setShown]=useState(false);
  useEffect(()=>{const el=ref.current;if(!el||!('IntersectionObserver' in window)){setShown(true);return;}const io=new IntersectionObserver(([e])=>{if(e.isIntersecting){setShown(true);io.disconnect();}},{threshold:.12});io.observe(el);return()=>io.disconnect();},[]);
  return <Tag ref={ref as never} className={`${className} sd-reveal ${shown?'sd-in':''}`} style={{transitionDelay:`${delay}ms`}} {...rest}>{shown?children:<div style={{minHeight:120}}/>}</Tag>;
}

export default function StudentDashboard(){
  const [profile,setProfile]=useState<Profile|null>(null);
  const [quizzes,setQuizzes]=useState<Quiz[]>([]);
  const [error,setError]=useState('');const [loading,setLoading]=useState(true);const [page,setPage]=useState(0);
  useEffect(()=>{
    let active=true;let pending=false;
    async function refresh(){
      if(pending)return;pending=true;
      try{
        const quiz=new URLSearchParams(window.location.search).get('quiz');
        const participant=quiz?loadParticipant(quiz):null;
        if(quiz&&!participant)throw new Error('Re-enter your quiz with your email to open its dashboard.');
        const data=await fetch('/api/v1/student/profile',{cache:'no-store',headers:participant?{'X-Participant-Token':participant.token}:{}}).then(readApiResponse<Profile>);
        const assigned=data.account?await fetch('/api/v1/student/quizzes').then(readApiResponse<Quiz[]>):[];
        if(active){setProfile(data);setQuizzes(assigned);setError('');}
      }catch(e){if(active){setProfile(null);setQuizzes([]);setError((e as Error).message);}}
      finally{pending=false;if(active)setLoading(false);}
    }
    void refresh();const timer=setInterval(refresh,15000);window.addEventListener('focus',refresh);
    return()=>{active=false;clearInterval(timer);window.removeEventListener('focus',refresh);};
  },[]);

  const charts=useMemo(()=>{
    const history=[...(profile?.history||[])].sort((a,b)=>Date.parse(a.date)-Date.parse(b.date));
    const short=(d:string)=>new Date(d).toLocaleDateString(undefined,{month:'short',day:'numeric'});
    const graded=history.filter(h=>h.status==='Completed'&&h.percentage!==null);
    return {
      trend:graded.slice(-12).map(h=>({label:short(h.date),value:Math.max(0,Math.min(100,h.percentage as number)),title:h.title})),
      bars:graded.slice(-8).map(h=>({label:short(h.date),value:h.points,title:h.title})),
      live:history.filter(h=>h.source==='live').length,
      assigned:history.filter(h=>h.source!=='live').length,
      completed:history.filter(h=>h.status==='Completed').length,
      pending:history.filter(h=>h.status!=='Completed').length,
    };
  },[profile]);

  if(loading)return <div className="sd-shell"><LoadingSkeleton label="Loading your learning hub…"/></div>;
  if(!profile)return <section className="panel sd-signin"><h2>Your personal dashboard</h2><p role="alert" className="error">{error}</p><a href="/">Sign in or create a student account</a><p>Use the same email you entered for your quizzes.</p></section>;
  const next=profile.next_achievement;const pages=Math.max(1,Math.ceil(profile.history.length/20));const currentPage=Math.min(page,pages-1);
  const available=quizzes.filter(q=>q.status!=='submitted');
  const initials=profile.name.split(/\s+/).map(s=>s[0]).join('').slice(0,2).toUpperCase();
  const hour=new Date().getHours();const greet=hour<12?'Good morning':hour<17?'Good afternoon':'Good evening';

  return <div className="student-profile sd-shell">
    {/* Hero */}
    <section className="sd-hero student-profile-heading" aria-labelledby="sd-name">
      <div className="sd-hero-orbs" aria-hidden="true"><span/><span/><span/></div>
      <div className="sd-hero-id">
        <div className="sd-avatar" aria-hidden="true"><span>{initials}</span></div>
        <div><span className="sd-kicker">{greet} · STUDENT PROFILE</span><h2 id="sd-name">{profile.name}</h2><p>{profile.email}</p><span className="sd-chip">{profile.performance}</span></div>
      </div>
      <div className={`sd-emblem achievement-emblem achievement-${(profile.achievement||'starter').toLowerCase()}`}>
        <Ring value={profile.completed_quizzes} max={next?.threshold||profile.completed_quizzes||1}><span aria-hidden="true">{icon(profile.achievement)}</span></Ring>
        <span className="sd-emblem-sparks" aria-hidden="true"><i/><i/><i/><i/></span><small className="sd-emblem-kicker">Current achievement</small><strong>{profile.achievement||'Getting started'}</strong>{next?<span className="sd-emblem-meta">{profile.completed_quizzes}/{next.threshold} to {next.name}</span>:<span className="sd-emblem-meta">Top tier reached</span>}
      </div>
      <a href="/join" className="sd-cta">Join a live quiz <span aria-hidden="true">→</span></a>
    </section>

    {/* KPI tiles */}
    <section aria-labelledby="performance-summary" className="sd-section">
      <div className="sd-head"><h2 id="performance-summary">Performance summary</h2><span className="sd-live-dot">Live · refreshes automatically</span></div>
      <div className="sd-kpis student-stats">
        {([['Quizzes attempted',profile.total_attempted,'','M4 6h16M4 12h16M4 18h10'],['Total points',profile.total_points,'','M12 3l2.7 5.6 6.3.9-4.5 4.4 1 6.1L12 17l-5.5 3 1-6.1L3 9.5l6.3-.9z'],['Average score',profile.average_score,'%','M4 19V9m6 10V5m6 14v-7m4 7H2'],['Highest score',profile.highest_score,'%','M5 15l7-7 7 7'],['Lowest score',profile.lowest_score,'%','M5 9l7 7 7-7'],['Completed quizzes',profile.completed_quizzes,'','M5 12l4 4L19 6']] as const).map(([label,value,suffix,d],i)=>
          <Reveal as="article" className="sd-kpi panel" key={label} delay={i*70}><span className="sd-kpi-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d={d}/></svg></span><span className="sd-kpi-label">{label}</span><strong><CountUp value={value} suffix={suffix}/></strong></Reveal>)}
      </div>
    </section>

    {/* Charts */}
    <div className="sd-grid">
      <Reveal className="sd-card sd-span-2" aria-labelledby="sd-trend-h"><div className="sd-card-head"><h3 id="sd-trend-h">Score trend</h3><span>Last {charts.trend.length||0} graded quizzes</span></div><TrendChart points={charts.trend}/></Reveal>
      <Reveal className="sd-card" delay={80} aria-labelledby="sd-gauge-h"><div className="sd-card-head"><h3 id="sd-gauge-h">Average accuracy</h3><span>{profile.performance}</span></div><Gauge value={profile.average_score} label="Average score"/>
        <div className="sd-minmax"><div><small>Lowest</small><b>{percent(profile.lowest_score)}</b></div><div className="sd-range"><i style={{left:`${profile.lowest_score??0}%`,width:`${Math.max(0,(profile.highest_score??0)-(profile.lowest_score??0))}%`}}/></div><div><small>Highest</small><b>{percent(profile.highest_score)}</b></div></div></Reveal>
      <Reveal className="sd-card" aria-labelledby="sd-bars-h"><div className="sd-card-head"><h3 id="sd-bars-h">Points earned</h3><span>Recent quizzes</span></div><Bars rows={charts.bars}/></Reveal>
      <Reveal className="sd-card" delay={80} aria-labelledby="sd-mix-h"><div className="sd-card-head"><h3 id="sd-mix-h">Quiz mix</h3><span>Live vs assigned</span></div><Donut center={profile.history.length} sub="attempts" segments={[{label:'Live quizzes',value:charts.live,tone:'t1'},{label:'Assigned quizzes',value:charts.assigned,tone:'t2'}]}/></Reveal>
      <Reveal className="sd-card" delay={160} aria-labelledby="sd-status-h"><div className="sd-card-head"><h3 id="sd-status-h">Completion</h3><span>Graded vs pending</span></div><Donut center={charts.completed} sub="completed" segments={[{label:'Completed',value:charts.completed,tone:'t3'},{label:'Pending',value:charts.pending,tone:'t4'}]}/></Reveal>
    </div>
    <p className="student-help sd-help">Each completed quiz earns its percentage rounded to whole points (0-100). Scores include speed bonuses and negative marks; percentages use the maximum available marks. Ungraded quizzes earn no points and are excluded from averages.</p>

    {/* Achievement journey */}
    <Reveal className="sd-card achievement-progress sd-journey" aria-labelledby="achievement-heading">
      <div className="sd-card-head"><h2 id="achievement-heading">Your achievement journey</h2>{next&&<span>Next: {next.name}</span>}</div>
      {next?<div className="sd-next"><div className="sd-next-badge">{icon(next.name)}</div><div className="sd-next-body"><span className="sd-next-kicker">Next unlock</span><p className="sd-next-line"><b>{next.remaining}</b> more {next.remaining===1?'quiz':'quizzes'} to reach <em>{next.name}</em></p><div className="achievement-progress-label"><strong>{profile.completed_quizzes} / {next.threshold} quizzes completed</strong><span>{Math.round(Math.min(100,profile.completed_quizzes/next.threshold*100))}%</span></div><AnimatedProgressBar label={`Progress toward ${next.name}`} max={next.threshold} value={profile.completed_quizzes}/></div></div>:<p>You reached Diamond, the highest achievement. Keep building your points!</p>}
      <ol className="sd-path achievement-levels">{Object.entries(profile.thresholds).map(([name,threshold],i)=><li className={profile.completed_quizzes>=threshold?'earned':''} key={name} style={{animationDelay:`${i*.15}s`}}><span className="sd-path-badge" aria-hidden="true">{icon(name)}<i className="sd-path-state">{profile.completed_quizzes>=threshold?<svg viewBox="0 0 16 16"><path d="M3.5 8.5l3 3 6-7"/></svg>:<svg viewBox="0 0 16 16"><rect x="3.5" y="7" width="9" height="6.5" rx="1.5"/><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2"/></svg>}</i></span><strong>{name[0].toUpperCase()+name.slice(1)}</strong><small>{threshold}+ completed quizzes</small></li>)}</ol>
    </Reveal>

    {/* Assigned quizzes */}
    {profile.account&&<section className="sd-section" aria-labelledby="sd-assigned"><div className="sd-head"><h2 id="sd-assigned">Assigned quizzes</h2><span className="sd-count">{available.length}</span></div>{!available.length&&<p className="sd-muted">No pending quizzes. Your completed quizzes are in your history below.</p>}<div className="assigned-quiz-list sd-assigned">{available.map((q,i)=><Reveal as="article" className={`sd-quiz panel sd-status-${q.status}`} key={q.id} delay={i*60}><span className="sd-quiz-status">{q.status}</span><h3>{q.title}</h3><p className="sd-quiz-meta"><span>{q.question_count} questions</span></p><p className="sd-quiz-time">{new Date(q.starts_at).toLocaleString()} – {new Date(q.ends_at).toLocaleString()}</p>{q.status==='open'&&<a href={`/quiz/${q.id}`} className="sd-quiz-open">Open quiz <span aria-hidden="true">→</span></a>}</Reveal>)}</div></section>}

    {/* History */}
    <section aria-labelledby="quiz-history" className="sd-section"><div className="sd-head"><h2 id="quiz-history">Quiz history</h2><span className="sd-count">{profile.history.length}</span></div>{!profile.history.length?<AnimatedEmptyState title="Your learning story starts here"><p>Your quiz history will appear after you start your first quiz.</p><a href="/join" className="secondary">Join a quiz</a></AnimatedEmptyState>:<><div className="table-wrap student-history sd-table"><table><caption className="student-help">Your individual results across live and assigned quizzes</caption><thead><tr>{['Quiz','Date','Score','Total marks','Percentage','Points','Status'].map(label=><th scope="col" key={label}>{label}</th>)}</tr></thead><tbody>{profile.history.slice(currentPage*20,(currentPage+1)*20).map(row=><tr key={`${row.source}-${row.id}`}><td data-label="Quiz">{row.source==='scheduled'?<a href={`/quiz/${row.quiz_id}`}>{row.title}</a>:row.title}<small className="student-quiz-type">{row.source==='live'?'Live quiz':'Assigned quiz'}</small></td><td data-label="Date">{new Date(row.date).toLocaleString()}</td><td data-label="Score">{row.status==='Completed'?`${row.score} / ${row.total_marks}`:'Pending'}</td><td data-label="Total marks">{row.total_marks}</td><td data-label="Percentage">{row.status==='Completed'?<span className="sd-pct"><i style={{width:`${Math.max(0,Math.min(100,row.percentage??0))*0.46}px`}}/>{percent(row.percentage)}</span>:'\u2014'}</td><td data-label="Points">{row.points}</td><td data-label="Status"><span className={`sd-badge ${row.status==='Completed'?'ok':'wait'}`}>{row.status}</span></td></tr>)}</tbody></table></div>{pages>1&&<div className="admin-pagination sd-pages"><span>Page {currentPage+1} of {pages}</span><div><button className="secondary" disabled={!currentPage} onClick={()=>setPage(currentPage-1)}>Previous</button><button className="secondary" disabled={currentPage+1>=pages} onClick={()=>setPage(currentPage+1)}>Next</button></div></div>}</>}</section>
  </div>;
}
