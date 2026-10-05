'use client';
import { FormEvent, useEffect, useState } from 'react';
import { readApiResponse } from './api-response';
import StudentDashboard from './student-dashboard';
import { getPostAuthPath } from './auth-routing';

type User = { id: string; name: string; email: string; profession: 'teacher' | 'student'; is_super_admin: boolean };
type Org = { id: string; name: string; role: string };
type Presentation = { id: string; title: string; revision: number; status: string };
type Department = { id: string; name: string };
type Member = { id: string; name: string; email: string; role: string };

async function api<T>(path: string, body?: object, method?: string): Promise<T> {
  const response = await fetch(`/api/v1${path}`, { method: method || (body ? 'POST' : 'GET'), credentials: 'include',
    headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined });
  return readApiResponse<T>(response);
}

export default function Home() {
  const [user, setUser] = useState<User | null>(null);
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [orgId, setOrgId] = useState('');
  const [items, setItems] = useState<Presentation[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [view, setView] = useState('Presentations');
  const [register, setRegister] = useState(false);
  const [profession, setProfession] = useState<'teacher' | 'student'>('teacher');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [editing, setEditing] = useState<Presentation | null>(null);
  const [creating, setCreating] = useState(false);
  const org = orgs.find(x => x.id === orgId);
  const manage = org && ['owner', 'admin'].includes(org.role);

  async function loadAccount() {
    const me = await api<User>('/auth/me');
    const destination = getPostAuthPath(me);
    if (destination !== '/') { window.location.replace(destination); return; }
    const organizations = me.profession === 'student' ? [] : await api<Org[]>('/organizations');
    setUser(me); setOrgs(organizations); setOrgId(organizations[0]?.id || '');
  }
  useEffect(() => { loadAccount().catch(e => { if (e.message !== 'Please sign in') setError(e.message); }).finally(() => setLoading(false)); }, []);
  useEffect(() => {
    if (!orgId) return;
    let current = true;
    setItems([]); setDepartments([]); setMembers([]); setError(''); setLoading(true);
    Promise.all([api<Presentation[]>(`/organizations/${orgId}/presentations`), api<Department[]>(`/organizations/${orgId}/departments`),
      manage ? api<Member[]>(`/organizations/${orgId}/members`) : Promise.resolve([])])
      .then(([p, d, m]) => { if (current) { setItems(p); setDepartments(d); setMembers(m); } })
      .catch(e => { if (current) setError(e.message); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [orgId, manage]);

  async function authenticate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('');
    const values = Object.fromEntries(new FormData(event.currentTarget));
    try { await api(register ? '/auth/register' : '/auth/login', values); await loadAccount(); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function savePresentation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('');
    const values = new FormData(event.currentTarget);
    const body = editing ? {title: values.get('title'), revision: editing.revision} : {title: values.get('title'), department_id: values.get('department_id') || null};
    try {
      const item = await api<Presentation>(`/organizations/${orgId}/presentations${editing ? `/${editing.id}` : ''}`, body, editing ? 'PATCH' : 'POST');
      setItems(old => editing ? old.map(x => x.id === item.id ? item : x) : [item, ...old]); setEditing(null); setCreating(false);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function createDepartment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = event.currentTarget; setBusy(true); setError('');
    try { const d = await api<Department>(`/organizations/${orgId}/departments`, {name: new FormData(form).get('name')}); setDepartments(old => [...old, d]); form.reset(); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  if (!user) return <main className="auth-layout">
    <section className="auth-story"><div className="wordmark"><span className="mark">Q</span> Quizeee</div><div><span className="eyebrow">THE TEACHING WORKSPACE</span><h1>Good questions.<br/>Great possibilities.</h1><p>A home for your presentations, your faculty, and your next big classroom idea.</p><div className="graphic" aria-hidden="true"><span>A</span><span>B</span><span>?</span><span>C</span></div></div><small>Built around the way you teach.</small></section>
    <section className="auth-form"><span className="eyebrow">YOUR WORKSPACE STARTS HERE</span><h2>{register ? 'Create your account' : 'Welcome back'}</h2><p>{register ? 'Choose how you will use Quizeee.' : 'Sign in to your Quizeee workspace.'}</p>
      {error && <p role="alert" className="error">{error}</p>}
      {loading ? <p role="status">Loading your workspace…</p> : <form onSubmit={authenticate}>
        {register && <><label>Your name<input name="name" required maxLength={120} autoComplete="name" /></label><fieldset><legend>I am a</legend><label><input type="radio" name="profession" value="teacher" checked={profession==='teacher'} onChange={()=>setProfession('teacher')}/> Teacher ? create and present quizzes</label><label><input type="radio" name="profession" value="student" checked={profession==='student'} onChange={()=>setProfession('student')}/> Student ? join classes and answer quizzes</label></fieldset>{profession==='teacher'&&<label>Organization<input name="organization" required maxLength={120} autoComplete="organization" /></label>}</>}
        <label>Email<input name="email" type="email" required autoComplete="email" /></label><label>Password<input name="password" type="password" required minLength={6} maxLength={128} pattern={register ? '(?=.*[a-z])(?=.*[A-Z])(?=.*\\d)(?=.*[^A-Za-z0-9]).{6,}' : undefined} title={register ? 'Use at least 6 characters with uppercase and lowercase letters, a number, and a symbol.' : undefined} autoComplete={register ? 'new-password' : 'current-password'} /></label>
        {register && <small>At least 6 characters, with uppercase and lowercase letters, a number, and a symbol.</small>}<button disabled={busy}>{busy ? 'Please wait…' : register ? 'Create account' : 'Sign in'}</button>
      </form>}
      <button className="text-button" onClick={() => {setRegister(!register); setError('');}}>{register ? 'Already have an account? Sign in' : 'New to Quizeee? Create an account'}</button>
    </section>
  </main>;

  if (user.profession === 'student') return <div className="workspace"><aside><div className="wordmark"><span className="mark">Q</span> Quizeee</div><nav aria-label="Student navigation"><button className="active">My dashboard</button><a href="/join">Join a quiz</a></nav><div className="sidebar-bottom"><strong>{user.name}</strong><small>Student</small><button className="text-button" onClick={async()=>{try{await api('/auth/logout',{});setUser(null);setOrgId('');setError('');}catch(e){setError((e as Error).message);}}}>Sign out</button></div></aside><main className="main"><header>Student dashboard</header><section className="content"><div className="page-heading"><div><span className="eyebrow">YOUR LEARNING SPACE</span><h1>Welcome, {user.name}</h1><p>Enter the code shared by your teacher to join a live quiz.</p></div></div>{error&&<p role="alert" className="error">{error}</p>}<StudentDashboard/><section className="panel"><h2>Join your class</h2><form action="/join" method="get"><label>Quiz code<input name="code" required pattern="[0-9]{6}" maxLength={6} inputMode="numeric" placeholder="6-digit code"/></label><button>Join quiz</button></form></section></section></main></div>;

  return <div className="workspace"><aside><div className="wordmark"><span className="mark">Q</span> Quizeee</div>
    <label className="org-label">WORKSPACE<select value={orgId} onChange={e => {setOrgId(e.target.value); setView('Presentations');}}>{orgs.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
    <nav aria-label="Workspace">{['Presentations', 'Departments', ...(manage ? ['Members'] : [])].map((x, i) => <button key={x} className={view === x ? 'active' : ''} onClick={() => {setView(x); setQuery('');}}><span aria-hidden="true">{['▤', '▦', '◎'][i]}</span>{x}</button>)}</nav><div className="actions"><a href={`/bank/${orgId}`}>Question bank</a><a href={`/analytics/${orgId}`}>Analytics</a></div>
    <div className="sidebar-bottom"><div className="avatar">{user.name.slice(0, 1)}</div><strong>{user.name}</strong><small>{org?.role.replaceAll('_', ' ')}</small><button className="text-button" onClick={async () => {try { await api('/auth/logout', {}); setUser(null); setOrgId(''); } catch(e) {setError((e as Error).message);}}} >Sign out</button></div>
  </aside><main className="main"><header><span>{org?.name} <span className="slash">/</span> {view}</span><span className="badge">Teacher dashboard</span></header>
    <section className="content"><div className="page-heading"><div><span className="eyebrow">YOUR TEACHING SPACE</span><h1>{view}</h1><p>{view === 'Presentations' ? 'Make room for your next idea.' : view === 'Departments' ? 'Organize your teaching community.' : 'The people in your organization.'}</p></div>{view === 'Presentations' && <button onClick={() => {setCreating(true); setEditing(null);}}>＋ New presentation</button>}</div>
    {error && <p role="alert" className="error">{error}</p>}
    {(creating || editing) && view === 'Presentations' && <section className="panel"><h2>{editing ? 'Rename presentation' : 'Start a presentation'}</h2><form onSubmit={savePresentation}><label>Title<input name="title" defaultValue={editing?.title || ''} required maxLength={160} autoFocus /></label>{!editing && <label>Department<select name="department_id"><option value="">No department</option>{departments.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label>}<div className="actions"><button disabled={busy}>Save</button><button type="button" className="secondary" onClick={() => {setCreating(false); setEditing(null);}}>Cancel</button></div></form></section>}
    {loading ? <p role="status">Loading…</p> : view === 'Presentations' ? <><div className="toolbar"><strong>All presentations <span className="count">{items.length}</span></strong><input aria-label="Search presentations" placeholder="Search presentations…" value={query} onChange={e => setQuery(e.target.value)} /></div>
      <div className="cards">{items.filter(x => x.title.toLowerCase().includes(query.toLowerCase())).map((x, i) => <article className="card" key={x.id}><div className={`cover cover-${i % 3}`}><span>QUIZEEE</span><h2>{x.title}</h2><small>Presentation draft</small></div><div className="card-info"><div><a href={`/editor/${orgId}/${x.id}`}><strong>{x.title}</strong></a><small>{x.status} · Revision {x.revision}</small></div><button className="secondary" onClick={() => {setEditing(x); setCreating(false);}}>Rename</button></div></article>)}</div>
      {!items.length && <section className="empty"><span className="empty-symbol" aria-hidden="true">＋</span><h2>Your first idea belongs here</h2><p>Create a presentation draft to start your library.</p><button onClick={() => setCreating(true)}>Create presentation</button></section>}
      {!!items.length && !items.some(x => x.title.toLowerCase().includes(query.toLowerCase())) && <p>No presentations match your search.</p>}
      <p className="development-note">Open a presentation to build questions and present a live session. Review completed sessions in Analytics.</p>
    </> : view === 'Departments' ? <>{manage && <form className="inline-form panel" onSubmit={createDepartment}><label>New department<input name="name" placeholder="e.g. Computer Science" maxLength={120} required /></label><button disabled={busy}>Add department</button></form>}<div className="department-list">{departments.map(d => <article className="panel" key={d.id}><span aria-hidden="true">▦</span><h2>{d.name}</h2></article>)}</div>{!departments.length && <p>No departments are available in your scope yet.</p>}</> : <div className="table-wrap"><table><thead><tr><th>Name</th><th>Email</th><th>Role</th></tr></thead><tbody>{members.map(m => <tr key={m.id}><td>{m.name}</td><td>{m.email}</td><td>{m.role.replaceAll('_', ' ')}</td></tr>)}</tbody></table></div>}
    </section></main></div>;
}



