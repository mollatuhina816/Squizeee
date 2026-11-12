'use client';
import { useEffect, useId, useState } from 'react';
import { ReconnectingIndicator } from './ui-primitives';

const messages = ['Sharpen your mind. The quiz is coming!', 'Ready to show what you know?', 'Great minds are warming up!', 'Your teacher will begin shortly.'];

export function AnimatedHourglass() {
  const id = useId().replaceAll(':', '');
  return <div className="hourglass-scene" aria-hidden="true"><span className="hourglass-orbit orbit-one"/><span className="hourglass-orbit orbit-two"/><span className="hourglass-star star-one">+</span><span className="hourglass-star star-two">+</span>
    <svg className="animated-hourglass" viewBox="0 0 220 260" fill="none">
      <defs><linearGradient id={`${id}-glass`} x1="55" y1="40" x2="170" y2="220" gradientUnits="userSpaceOnUse"><stop stopColor="#EFF6FF"/><stop offset=".5" stopColor="#E0E7FF" stopOpacity=".45"/><stop offset="1" stopColor="#C4B5FD"/></linearGradient><linearGradient id={`${id}-sand`} x1="65" y1="60" x2="160" y2="200" gradientUnits="userSpaceOnUse"><stop stopColor="#8B5CF6"/><stop offset="1" stopColor="#4F46E5"/></linearGradient><clipPath id={`${id}-clip`}><path d="M63 49h94c0 46-19 59-39 79v4c20 20 39 33 39 79H63c0-46 19-59 39-79v-4C82 108 63 95 63 49Z"/></clipPath></defs>
      <ellipse cx="110" cy="241" rx="65" ry="8" fill="#4F46E5" opacity=".08"/>
      <g className="hourglass-body"><path d="M63 49h94c0 46-19 59-39 79v4c20 20 39 33 39 79H63c0-46 19-59 39-79v-4C82 108 63 95 63 49Z" fill={`url(#${id}-glass)`} stroke="#A5B4FC" strokeWidth="2"/>
        <g clipPath={`url(#${id}-clip)`}><path className="sand-upper" d="M60 68h100l-50 64-50-64Z" fill={`url(#${id}-sand)`}/><path className="sand-lower" d="m110 167 56 48H54l56-48Z" fill={`url(#${id}-sand)`}/><path className="sand-stream" d="M110 127v51" stroke="#8B5CF6" strokeWidth="2" strokeDasharray="3 5"/><circle className="sand-particle particle-one" cx="106" cy="140" r="2" fill="#06B6D4"/><circle className="sand-particle particle-two" cx="114" cy="140" r="1.5" fill="#8B5CF6"/></g>
        <path d="M73 58c0 28 7 40 17 51M145 151c7 10 9 23 9 37" stroke="white" strokeWidth="5" strokeLinecap="round" opacity=".85"/>
        <rect x="49" y="32" width="122" height="17" rx="8.5" fill="#4F46E5"/><rect x="49" y="211" width="122" height="17" rx="8.5" fill="#4F46E5"/><path d="M60 38h99M60 217h99" stroke="#A5B4FC" strokeWidth="2" strokeLinecap="round"/>
      </g>
    </svg>
  </div>;
}

export default function StudentQuizWaitingRoom({ connection, nickname, title, participantCount, code }: { connection: string; nickname?: string; title?: string; participantCount?: number; code?: string }) {
  const [message, setMessage] = useState(0);
  useEffect(() => {
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let timer: ReturnType<typeof setInterval> | undefined;
    const update = () => {
      clearInterval(timer);
      if (!document.hidden && !motion.matches) timer = setInterval(() => setMessage(index => (index + 1) % messages.length), 6000);
    };
    update(); document.addEventListener('visibilitychange', update); motion.addEventListener('change', update);
    return () => { clearInterval(timer); document.removeEventListener('visibilitychange', update); motion.removeEventListener('change', update); };
  }, []);
  return <section className="student-waiting-room" aria-labelledby="waiting-room-title"><ReconnectingIndicator connection={connection}/><AnimatedHourglass/><span className="eyebrow">YOUR NEXT CHALLENGE</span><h1 id="waiting-room-title">You&apos;re In!</h1><p className="waiting-description">Waiting for your teacher to start the quiz...</p><p>Get ready! Your challenge is about to begin.</p>{title && <h2 className="waiting-quiz-title">{title}</h2>}
    <dl className="waiting-details">{nickname && <div><dt>Playing as</dt><dd>{nickname}</dd></div>}{participantCount !== undefined && <div><dt>In the room</dt><dd>{participantCount} {participantCount === 1 ? 'participant' : 'participants'}</dd></div>}{code && <div><dt>Session code</dt><dd>{code}</dd></div>}</dl>
    <p className="waiting-message" key={message}>{messages[message]}</p><small>Your place is saved. This screen updates when your teacher begins.</small>
  </section>;
}
