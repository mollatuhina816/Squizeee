'use client';
import { useEffect } from 'react';

// Decorative motion only: never owns navigation, credentials or quiz state.
export default function VisualRuntime() {
  useEffect(() => {
    const update = () => { document.documentElement.dataset.motionPaused = String(document.hidden); };
    update();
    document.addEventListener('visibilitychange', update);
    return () => { document.removeEventListener('visibilitychange', update); delete document.documentElement.dataset.motionPaused; };
  }, []);
  return null;
}
