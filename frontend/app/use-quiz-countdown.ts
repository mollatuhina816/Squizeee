'use client';
import { useEffect, useState } from 'react';
import { countdownSeconds } from './countdown';

export function useQuizCountdown(serverTime?: string, openedAt?: string | null, durationSeconds?: number, pausedAt?: string | null) {
  const [remaining, setRemaining] = useState(0);
  useEffect(() => {
    if (!serverTime || !openedAt || durationSeconds === undefined) { setRemaining(0); return; }
    const receivedAt = performance.now();
    const update = () => setRemaining(countdownSeconds(pausedAt || serverTime, openedAt, durationSeconds, pausedAt ? 0 : performance.now() - receivedAt));
    update();
    const timer = setInterval(update, 250);
    document.addEventListener('visibilitychange', update);
    return () => { clearInterval(timer); document.removeEventListener('visibilitychange', update); };
  }, [serverTime, openedAt, durationSeconds, pausedAt]);
  return remaining;
}
