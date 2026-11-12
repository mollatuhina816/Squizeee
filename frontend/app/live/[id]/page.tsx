'use client';
import { authFetch } from '../../auth-fetch';
import { useParams } from 'next/navigation';
import styles from '../../live-engagement.module.css';
import Link from 'next/link';
import FullscreenCard from '../../fullscreen-card';
import CopyLinkButton from '../../copy-link-button';
import { useLiveSocket } from '../../use-live-socket';
import { readApiResponse } from '../../api-response';
import { QRCodeSVG } from 'qrcode.react';
import { LoadingSkeleton, ReconnectingIndicator } from '../../ui-primitives';
import { AnimatedRankings, AudiencePanel, RandomPicker, ReactionOverlay, useEngagementEvents, type RankedParticipant } from '../../live-engagement';
import { LiveResults, type DisplayQuestion, type Pin } from '../../live-formats';
import LivePieChart from '../../live-pie-chart';
import { useCallback, useEffect, useState } from 'react';

type Snapshot = {
 total_responses:number; completed_count:number; state:string; revision:number; active_index:number; question_count:number;
 join_code:string|null; participant_count:number; question:DisplayQuestion|null; responses:{answer:unknown;correct:boolean|null}[];
 leaderboard:RankedParticipant[]; teams:(RankedParticipant & {color:string;members:number})[];
 delivery_mode:string; opened_at:string|null; paused_at:string|null; server_time:string; revealed:boolean;
 reveal:{correct_answers:string[];explanation:string;hotspot_target?:Pin & {radius:number}}|null;
 speaker_notes:string; next_question:DisplayQuestion|null;
};
export default function Present(){
 const {id}=useParams<{id:string}>();
 const [data,setData]=useState<Snapshot|null>(null);const [error,setError]=useState('');const [busy,setBusy]=useState(false);const [origin,setOrigin]=useState('');const [remote,setRemote]=useState(false);
 const engagement=useEngagementEvents();
 useEffect(()=>{setOrigin(location.origin);setRemote(new URLSearchParams(location.search).get('remote')==='1');},[]);
 const refresh=useCallback(async()=>{try{const d=await readApiResponse<Snapshot>(await authFetch(`/api/v1/sessions/${id}/host`));setData(old=>old&&old.revision>d.revision?old:d);setError('');}catch(e){setError((e as Error).message);}},[id]);
 useEffect(()=>{void refresh();const timer=setInterval(refresh,5000);return()=>clearInterval(timer);},[refresh]);
 const connection=useLiveSocket<Snapshot>(`/api/v1/sessions/${id}/host-ticket`,undefined,()=>{void refresh();},refresh,engagement.onEvent);
 async function control(action:string){if(!data)return;setBusy(true);try{await readApiResponse(await authFetch(`/api/v1/sessions/${id}/control`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,revision:data.revision})}));await refresh();}catch(e){await refresh();setError((e as Error).message);}finally{setBusy(false);}}
 const guided=data?.delivery_mode==='guided';
 return <main className={`live-page ${styles.host}`}><ReactionOverlay events={engagement.events}/><header><Link href="/">{"\u2190"} Workspace</Link><strong>{remote?'Presenter remote':'Quizeee Live'}</strong><div className="actions"><a href={`/live/${id}${remote?'':'?remote=1'}`} target="_blank" rel="noreferrer">{remote?'Open main display':'Open private remote'} {"\u2197"}</a><button className="secondary" onClick={()=>void document.documentElement.requestFullscreen()}>Full screen</button></div></header>
 <section className="live-content"><div className="live-heading"><div><span className="eyebrow">{remote?'PRIVATE HOST CONTROLS':'PRESENTER SPACE'}</span><h1>{remote?'Your presenter remote':'Quizeee Live'}</h1></div><ReconnectingIndicator connection={connection}/></div>
 {error&&<p className="error" role="alert">{error}</p>}{!data?<LoadingSkeleton label="Loading your live session..."/>:<>
 <FullscreenCard title="Room and participants"><div className="live-top"><div><span className="eyebrow">JOIN AT /JOIN</span><strong className="join-code">{data.join_code||'Session ended'}</strong>{data.join_code&&<p><a href={`/join?code=${data.join_code}`} target="_blank" rel="noreferrer">Open participant link {"\u2197"}</a> <CopyLinkButton url={origin?`${origin}/join?code=${data.join_code}`:''}/></p>}</div><div>{data.join_code&&origin&&<QRCodeSVG value={`${origin}/join?code=${data.join_code}`} size={140} marginSize={2} title="Scan to join this session"/>}</div><div className="live-count"><strong>{data.participant_count}</strong><span>participants</span></div></div></FullscreenCard>
 <FullscreenCard title="Question results" className="slide-preview"><span className="eyebrow">Question {data.active_index+1} of {data.question_count} / {data.state}</span><h1>{data.question?.title||(data.state==='ended'?'Thanks for taking part!':'Ready when you are.')}</h1>{data.question?.body&&<p>{data.question.body}</p>}{data.state==='question'&&<p>Students can read the question. Reveal options when you are ready to accept answers. There is no question time limit.</p>}{data.question&&data.state!=='question'&&<LiveResults question={data.question} responses={data.responses} target={data.reveal?.hotspot_target}/>}
 {data.reveal&&<section className="panel"><h2>Answer reveal</h2>{data.reveal.correct_answers.length>0&&<p>{data.reveal.correct_answers.join(' > ')}</p>}<p>{data.reveal.explanation}</p></section>}</FullscreenCard>
 <p><strong>{guided?'Presenter-paced':'Self-paced'}</strong>{' · '}{guided?'Show the question first, reveal options to start answering, then move everyone to the next question. There is no question countdown. Reveal correct answer is optional after closing answers.':'Students advance automatically after each answer. End session closes the quiz for everyone.'}</p>
 <div className="live-controls"><span>{data.total_responses} answers saved / {data.completed_count} of {data.participant_count} finished</span><div className="actions">
 <button disabled={busy||data.state!=='waiting'} onClick={()=>control(guided?'show_question':'open')}>{guided?'Show question':'Start quiz'}</button>
 {guided&&<button disabled={busy||data.state!=='question'} onClick={()=>control('reveal_options')}>Reveal options</button>}<button className="secondary" disabled={busy||data.state!=='open'} onClick={()=>control('close')}>Close answers</button>
 {data.state==='closed'&&!data.revealed&&<button className="secondary" disabled={busy} onClick={()=>control('reopen')}>Reopen answers</button>}
 {guided&&<><button className="secondary" disabled={busy||data.state!=='open'} onClick={()=>control(data.paused_at?'resume':'pause')}>{data.paused_at?'Resume answers':'Pause answers'}</button><button className="secondary" disabled={busy||data.state!=='closed'||data.revealed} onClick={()=>control('reveal')}>Reveal correct answer</button><button className="secondary" disabled={busy||!['question','open','closed'].includes(data.state)||data.active_index+1>=data.question_count} onClick={()=>control('next_question')}>Next question</button></>}
 <button className="secondary" disabled={busy||data.state==='ended'} onClick={()=>{if(window.confirm('End this session?'))void control('end');}}>End session</button></div></div>
 {remote&&<FullscreenCard title="Speaker notes" className="panel"><p style={{whiteSpace:'pre-wrap'}}>{data.speaker_notes||'No speaker notes for this slide.'}</p><h3>Up next</h3><p>{data.next_question?.title||'This is the final slide.'}</p></FullscreenCard>}
 <div className="live-row live-row-split"><FullscreenCard className="panel live-card" title={data.state==='ended'?'Final leaderboard':'Live leaderboard'}>{data.leaderboard.length?<AnimatedRankings rows={data.leaderboard}/>:<p>Scores appear as participants answer. Speed bonuses reward fast, correct answers.</p>}</FullscreenCard>
 <FullscreenCard className="panel live-card" title="Live performance"><LivePieChart rows={data.leaderboard}/></FullscreenCard></div>
 {!!data.teams?.length&&<div className="live-row"><FullscreenCard className="panel" title="Team competition / average points">{data.teams.map((t,i)=><p key={t.id} style={{borderLeft:`5px solid ${t.color}`,paddingLeft:12}}>#{i+1} {t.nickname} / {(t.score/1000).toFixed(2)} points / {t.members} members</p>)}</FullscreenCard></div>}
 <div className="live-row live-row-pair"><RandomPicker sessionId={id} rows={data.leaderboard} winner={engagement.winner} onEvent={engagement.onEvent}/>
 <AudiencePanel sessionId={id} host displayOnly={!remote} signal={data.server_time} ended={data.state==='ended'}/></div>
 </>}</section></main>;
}
