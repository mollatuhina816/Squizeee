'use client';

import Link from 'next/link';
import FullscreenCard from '../fullscreen-card';
import { FormEvent, useEffect, useState } from 'react';
import { readApiResponse } from '../api-response';
import AchievementSettings from './achievement-settings';
import { LoadingSkeleton } from '../ui-primitives';

type AdminUser = {
  id: string;
  name: string;
  email: string;
  profession: 'teacher' | 'student';
  active: boolean;
  is_super_admin: boolean;
  created_at: string;
  last_login_at: string | null;
  organizations: { name: string; role: string }[];
};

type Participant = {
  id: string;
  name: string;
  nickname: string;
  email: string | null;
  phone: string | null;
  stream: string | null;
  semester: string | null;
  institution_name: string | null;
  session_id: string;
  presentation: string;
  joined_at: string;
  score: number;
};

type Directory<T> = { items: T[]; total: number; limit: number; offset: number };
type View = 'accounts' | 'participants';

const pageSize = 50;

function date(value: string | null) {
  return value ? new Date(value).toLocaleString() : 'Never';
}

async function fetchDirectory<T>(url: string) {
  const response = await fetch(url, { credentials: 'include', cache: 'no-store' });
  return readApiResponse<T>(response);
}

export default function AdminDashboard() {
  const [authorized, setAuthorized] = useState(false);
  const [view, setView] = useState<View>('participants');
  const [refresh, setRefresh] = useState(0);
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [profession, setProfession] = useState('');
  const [summary, setSummary] = useState<{teachers:number;students:number;organizations:number;participants:number;active_accounts:number}|null>(null);
  const [offset, setOffset] = useState(0);
  const [accounts, setAccounts] = useState<Directory<AdminUser> | null>(null);
  const [participants, setParticipants] = useState<Directory<Participant> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!authorized) return;
    const reload = () => setRefresh(value => value + 1);
    const timer = window.setInterval(reload, 15000);
    window.addEventListener('focus', reload);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener('focus', reload);
    };
  }, [authorized]);

  useEffect(() => {
    let current = true;
    fetchDirectory<{ is_super_admin: boolean }>('/api/v1/auth/me')
      .then(user => {
        if (!current) return;
        if (user.is_super_admin) setAuthorized(true);
        else window.location.replace('/');
      })
      .catch(() => { if (current) window.location.replace('/'); });
    return () => { current = false; };
  }, []);

  useEffect(() => {
    if (!authorized) return;
    let current = true;
    fetchDirectory<typeof summary>('/api/v1/admin/summary').then(data=>{if(current)setSummary(data);}).catch(e=>{if(current)setError(e.message);});
    return ()=>{current=false;};
  }, [authorized, refresh]);

  useEffect(() => {
    if (!authorized) return;
    let current = true;
    setLoading(true);
    setError('');
    const params = new URLSearchParams({ q: query, limit: String(pageSize), offset: String(offset) });
    if (view === 'accounts' && profession) params.set('profession', profession);
    const endpoint = view === 'accounts' ? 'users' : 'participants';
    fetchDirectory<Directory<AdminUser | Participant>>(`/api/v1/admin/${endpoint}?${params}`)
      .then(result => {
        if (!current) return;
        if (view === 'accounts') setAccounts(result as Directory<AdminUser>);
        else setParticipants(result as Directory<Participant>);
      })
      .catch(error => { if (current) { setAccounts(null); setParticipants(null); setError((error as Error).message); } })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [authorized, view, query, offset, profession, refresh]);

  function searchDirectory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setOffset(0);
    setQuery(search.trim());
  }

  async function signOut() {
    try {
      const response = await fetch('/api/v1/auth/logout', { method: 'POST', credentials: 'include' });
      await readApiResponse(response);
      window.location.replace('/');
    } catch(e) { setError((e as Error).message); }
  }

  const directory = view === 'accounts' ? accounts : participants;
  const total = directory?.total ?? 0;

  if (!authorized) return <main className="admin-page"><div className="admin-content"><LoadingSkeleton label="Checking admin access…" rows={1}/></div></main>;

  return <main className="admin-page">
    <header className="admin-header">
      <Link href="/" className="wordmark"><span className="mark">Q</span> Quizeee</Link>
      <div><span className="admin-badge">SUPER ADMIN</span><button className="secondary" onClick={signOut}>Sign out</button></div>
    </header>
    <section className="admin-content">
      <div className="admin-heading">
        <div><span className="eyebrow">GLOBAL OPERATIONS</span><h1>Admin dashboard</h1><p>Account records and live-quiz participant details.</p></div>
        <div className="admin-total"><strong>{total.toLocaleString()}</strong><span>{view === 'accounts' ? 'login accounts' : 'quiz signups'}</span></div>
      </div>
      {summary&&<div className="admin-stats">{[['Teachers',summary.teachers],['Student accounts',summary.students],['Organizations',summary.organizations],['Student profiles',summary.participants],['Active accounts',summary.active_accounts]].map(([label,value])=><FullscreenCard className="panel report-metric" key={label} title={String(label)}><strong>{value}</strong></FullscreenCard>)}</div>}
      <AchievementSettings/>
      <FullscreenCard title={view==='accounts'?'Login accounts report':'Live quiz students report'}><nav className="admin-tabs" aria-label="Admin directories">
        <button className={view === 'accounts' ? 'active' : ''} onClick={() => { setView('accounts'); setOffset(0); }}>Login accounts</button>
        <button className={view === 'participants' ? 'active' : ''} onClick={() => { setView('participants'); setOffset(0); }}>Live quiz students</button>
        <button className="secondary" onClick={() => setRefresh(value => value + 1)} disabled={loading}>Refresh</button>
      </nav>
      <p>Live quiz students includes guest participants and their saved contact details, stream, semester, and scores. Student accounts counts students who created a login. This dashboard refreshes every 15 seconds.</p>
      {view==='accounts'&&<label className="admin-filter">Account type<select aria-label="Account type" value={profession} onChange={event=>{setProfession(event.target.value);setOffset(0);}}><option value="">All teachers and students</option><option value="teacher">Teachers</option><option value="student">Students</option></select></label>}
      <form className="admin-search" onSubmit={searchDirectory}>
        <label htmlFor="admin-search">Search {view === 'accounts' ? 'name or email' : 'name, email, phone, stream, semester, institute, or presentation'}</label>
        <div><input id="admin-search" value={search} onChange={event => setSearch(event.target.value)} maxLength={100} />
          <button type="submit">Search</button></div>
      </form>
      {error && <p role="alert" className="error">{error}</p>}
      {loading ? <LoadingSkeleton label="Loading the directory…"/> : view === 'accounts' ? <div className="table-wrap admin-table-wrap">
        <table><thead><tr><th>Name</th><th>Email</th><th>Type</th><th>Organizations</th><th>Status</th><th>Registered</th><th>Last login</th></tr></thead>
          <tbody>{accounts?.items.map(account => <tr key={account.id}>
            <td>{account.name}{account.is_super_admin && <span className="admin-inline-badge">Super admin</span>}</td>
            <td>{account.email}</td><td>{account.profession}</td>
            <td>{account.organizations.length ? account.organizations.map(org => `${org.name} (${org.role.replaceAll('_', ' ')})`).join(', ') : 'None'}</td>
            <td>{account.active ? 'Active' : 'Disabled'}</td><td>{date(account.created_at)}</td><td>{date(account.last_login_at)}</td>
          </tr>)}</tbody>
        </table>
        {!accounts?.items.length && <p className="admin-empty">No login accounts found.</p>}
      </div> : <div className="table-wrap admin-table-wrap">
        <table><thead><tr><th>Name</th><th>Nickname</th><th>Email</th><th>Phone</th><th>Institute</th><th>Stream</th><th>Semester</th><th>Quiz / presentation</th><th>Joined</th><th>Score</th></tr></thead>
          <tbody>{participants?.items.map(participant => <tr key={participant.id}>
            <td>{participant.name}</td><td>{participant.nickname}</td><td>{participant.email || 'Not provided'}</td>
            <td>{participant.phone || 'Not provided'}</td><td>{participant.institution_name || 'Not provided'}</td>
            <td>{participant.stream || 'Not provided'}</td>
            <td>{participant.semester || 'Not provided'}</td><td>{participant.presentation}</td>
            <td>{date(participant.joined_at)}</td><td>{(participant.score / 1000).toFixed(3)}</td>
          </tr>)}</tbody>
        </table>
        {!participants?.items.length && <p className="admin-empty">No quiz signups found.</p>}
      </div>}
      <footer className="admin-pagination"><span>{total ? `${offset + 1}–${Math.min(offset + pageSize, total)} of ${total}` : '0 results'}</span>
        <div><button className="secondary" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - pageSize))}>Previous</button>
          <button className="secondary" disabled={offset + pageSize >= total || loading} onClick={() => setOffset(offset + pageSize)}>Next</button></div>
      </footer></FullscreenCard>
      <p className="admin-privacy">This global view contains personal information. Use it only for authorized administration.</p>
    </section>
  </main>;
}
