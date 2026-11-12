'use client';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useDialogFocus } from './use-dialog-focus';
import styles from './fullscreen-card.module.css';

/** Expands the existing card in place so live updates and form state stay intact. */
export default function FullscreenCard({ title, children, className = '' }: { title: string; children: ReactNode; className?: string }) {
  const [expanded, setExpanded] = useState(false);
  const native = useRef(false);
  const card = useDialogFocus(expanded);
  useEffect(() => {
    function changed() {
      if (document.fullscreenElement === card.current) native.current = true;
      else if (native.current) { native.current = false; setExpanded(false); }
    }
    document.addEventListener('fullscreenchange', changed);
    return () => document.removeEventListener('fullscreenchange', changed);
  }, [card]);
  async function close() {
    if (document.fullscreenElement === card.current) {
      try { await document.exitFullscreen(); } catch { /* The in-page view can still close. */ }
    }
    native.current = false;
    setExpanded(false);
  }
  async function expand() {
    setExpanded(true);
    try { await card.current?.requestFullscreen?.(); } catch { /* Fall back to the in-page full-screen view. */ }
  }
  return <section ref={card} className={`${className} ${styles.card} ${expanded ? styles.expanded : ''}`} role={expanded ? 'dialog' : undefined} aria-modal={expanded ? true : undefined} aria-label={title} tabIndex={expanded ? -1 : undefined} onKeyDown={e => { if (expanded && e.key === 'Escape') { e.preventDefault(); void close(); } }}>
    <div className={styles.toolbar}><h2>{title}</h2><button type="button" className="secondary" aria-label={`${expanded ? 'Exit full screen' : 'Full screen'}: ${title}`} aria-expanded={expanded} onClick={() => void (expanded ? close() : expand())}>
      <svg aria-hidden="true" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8"><path d={expanded ? 'M9 3v6H3M15 3v6h6M9 21v-6H3M15 21v-6h6' : 'M3 9V3h6M21 9V3h-6M3 15v6h6M21 15v6h-6'}/></svg><span>{expanded ? 'Exit full screen' : 'Full screen'}</span>
    </button></div>
    <div className={styles.body}>{children}</div>
  </section>;
}
