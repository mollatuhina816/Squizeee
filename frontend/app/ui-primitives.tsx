import type { ReactNode } from 'react';

export function AcademicIcon({ kind = 'book', className = '' }: { kind?: 'book' | 'spark' | 'chart' | 'people'; className?: string }) {
  const paths = {
    book: <><path d="M12 6c-3-2-6-2-9-1v14c3-1 6-1 9 1 3-2 6-2 9-1V5c-3-1-6-1-9 1Z"/><path d="M12 6v14M6 9h3M15 9h3M6 12h3M15 12h3"/></>,
    spark: <><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z"/><path d="m20 2 .6 1.4L22 4l-1.4.6L20 6l-.6-1.4L18 4l1.4-.6Z"/></>,
    chart: <><path d="M4 4v16h16M8 16v-4M12 16V8M16 16v-6"/><path d="m7 8 5-4 5 2"/></>,
    people: <><circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6M18 14a5 5 0 0 1 3 4v2"/></>,
  };
  return <svg className={`academic-icon ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[kind]}</svg>;
}

export function FloatingAcademicShapes() {
  return <div className="academic-shapes" aria-hidden="true"><span><AcademicIcon/></span><span>π</span><span><AcademicIcon kind="spark"/></span><span>÷</span><span>∑</span><span className="academic-ring"/></div>;
}

export function LoadingSkeleton({ label = 'Loading…', rows = 3 }: { label?: string; rows?: number }) {
  return <div className="loading-state" role="status"><span className="loading-label">{label}</span><div className="skeleton-grid" aria-hidden="true">{Array.from({ length: rows }, (_, index) => <div className="skeleton-card" key={index}><span/><span/><span/></div>)}</div></div>;
}

export function ProcessingIndicator({ children }: { children: ReactNode }) {
  return <div className="processing-indicator" role="status"><span className="processing-symbol"><AcademicIcon kind="spark"/></span><div><strong>{children}</strong><small>This may take a moment. Your results will appear when ready.</small></div><span className="processing-track" aria-hidden="true"/></div>;
}

export function AnimatedEmptyState({ title, children, icon = 'book' }: { title: string; children: ReactNode; icon?: 'book' | 'spark' | 'chart' | 'people' }) {
  return <div className="empty premium-empty"><span className="empty-art"><AcademicIcon kind={icon}/></span><h2>{title}</h2><div className="empty-copy">{children}</div></div>;
}

export function ReconnectingIndicator({ connection }: { connection: string }) {
  const live = connection === 'Live';
  return <span className={`connection-pill ${live ? 'is-connected' : 'is-reconnecting'}`} role="status"><span className="connection-dot" aria-hidden="true"/>{live ? 'Live connection' : connection === 'Connecting' ? 'Connecting…' : 'Reconnecting…'}</span>;
}

export function AnimatedProgressBar({ value, max, label }: { value: number; max: number; label: string }) {
  return <progress className="animated-progress" value={value} max={Math.max(1, max)} aria-label={label}/>;
}

export function QuestionTypeBadge({ kind }: { kind: string }) {
  const tone = ['mcq', 'multiple_select', 'true_false', 'quiz'].includes(kind) ? 'choice' : ['poll', 'rating', 'scale', 'nps'].includes(kind) ? 'opinion' : 'text';
  return <span className={`question-type type-${tone}`}>{kind.replaceAll('_', ' ')}</span>;
}
