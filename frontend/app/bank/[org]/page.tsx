'use client';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import QuestionImporter from '../../question-importer';
import AIQuestionGenerator from '../../ai-question-generator';
import { useCallback, useEffect, useState } from 'react';
type BankItem={id:string;question:{title:string;kind:string};subject:string;chapter:string;topic:string;difficulty:string};
export default function Bank(){const {org}=useParams<{org:string}>();const [items,setItems]=useState<BankItem[]>([]);const [error,setError]=useState('');const [search,setSearch]=useState('');
 const refresh=useCallback(()=>fetch(`/api/v1/organizations/${org}/bank/questions`).then(async r=>{const d=await r.json();if(!r.ok)throw Error(d.detail);setItems(d);}).catch(e=>setError(e.message)),[org]);useEffect(()=>{refresh();},[refresh]);
 return <main><header><Link href="/">← Workspace</Link><strong>Question bank</strong></header><section className="content"><h1>Good questions, ready to reuse.</h1>{error&&<p role="alert" className="error">{error}</p>}<div className="bank-actions"><QuestionImporter org={org} onImported={()=>{refresh();}}/><AIQuestionGenerator org={org} onSaved={refresh}/></div><div className="toolbar"><strong>{items.length} questions</strong><input aria-label="Search question bank" placeholder="Search questions, subjects, topics…" value={search} onChange={e=>setSearch(e.target.value)}/></div><div className="table-wrap"><table><thead><tr><th>Question</th><th>Subject</th><th>Chapter / Topic</th><th>Difficulty</th></tr></thead><tbody>{items.filter(x=>`${x.question.title} ${x.subject} ${x.topic}`.toLowerCase().includes(search.toLowerCase())).map(x=><tr key={x.id}><td>{x.question.title}<small className="block">{x.question.kind}</small></td><td>{x.subject||'—'}</td><td>{x.chapter} / {x.topic}</td><td>{x.difficulty}</td></tr>)}</tbody></table></div>{!items.length&&<p>Save questions from the editor or import a question file to begin.</p>}</section></main>;
}
