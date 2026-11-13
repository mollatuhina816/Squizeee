'use client';
import { useState } from 'react';
import { useDialogFocus } from './use-dialog-focus';
import styles from './slide-type-picker.module.css';

const groups = [
  { title: 'Interactive questions', items: [
    { kind: 'mcq', label: 'Multiple Choice', icon: '▥', color: '#7852ba' },
    { kind: 'word_cloud', label: 'Word Cloud', icon: '✿', color: '#ee5e72' },
    { kind: 'short_answer', label: 'Open Ended', icon: '●', color: '#ec79ab' },
    { kind: 'scale', label: 'Scales', icon: '▣', color: '#9181cf' },
    { kind: 'ranking', label: 'Ranking', icon: '⚑', color: '#13ad88' },
    { kind: 'hotspot', label: 'Pin on Image', icon: '⌖', color: '#7852ba' },
    { kind: 'rating', label: 'Rating', icon: '★', color: '#e6ac36' },
    { kind: 'multiple_select', label: 'Multiple Select', icon: '☷', color: '#4a85d1' },
    { kind: 'nps', label: 'NPS', icon: '↗', color: '#df718e' },
  ] },
  { title: 'Quiz competitions', items: [
    { kind: 'quiz', label: 'Select Answer', icon: '▥', color: '#7852ba' },
    { kind: 'short_answer', label: 'Type Answer', icon: '↧', color: '#15a58e' },
    { kind: 'true_false', label: 'True / False', icon: '◐', color: '#4a85d1' },
  ] },
  { title: 'Content slides', items: [
    { kind: 'content', label: 'Text & Content', icon: 'T', color: '#65728a' },
  ] },
];

export default function SlideTypePicker({ disabled, onSelect }: { disabled?: boolean; onSelect: (kind: string) => void }) {
  const [open, setOpen] = useState(false);
  const dialog = useDialogFocus(open);
  return <div className={styles.anchor}>
    <button type="button" className={styles.trigger} disabled={disabled} aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen(true)}>＋ New slide</button>
    {open && <div className={styles.backdrop} onClick={() => setOpen(false)}>
      <section ref={dialog} className={styles.picker} role="dialog" aria-modal="true" aria-labelledby="slide-picker-title" tabIndex={-1} onClick={e => e.stopPropagation()} onKeyDown={e => { if (e.key === 'Escape') { e.stopPropagation(); setOpen(false); } }}>
        <div className={styles.heading}><h2 id="slide-picker-title">Choose a slide type</h2><button type="button" aria-label="Close slide picker" onClick={() => setOpen(false)}>×</button></div>
        {groups.map(group => <div className={styles.group} key={group.title}>
          <h3>{group.title}</h3>
          <div className={styles.grid}>{group.items.map(item => <button type="button" key={item.label} disabled={disabled} onClick={() => { onSelect(item.kind); setOpen(false); }}>
            <span aria-hidden="true" style={{ color: item.color }}>{item.icon}</span>{item.label}
          </button>)}</div>
        </div>)}
      </section>
    </div>}
  </div>;
}
