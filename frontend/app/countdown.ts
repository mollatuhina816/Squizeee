// Presentation-only countdown. The server remains the deadline authority.
export function countdownSeconds(serverTime: string, openedAt: string | null, durationSeconds: number, elapsedLocalMs: number) {
  if (!openedAt) return 0;
  const elapsedServerMs = Date.parse(serverTime) - Date.parse(openedAt);
  if (!Number.isFinite(elapsedServerMs) || !Number.isFinite(durationSeconds)) return 0;
  return Math.max(0, Math.min(durationSeconds, durationSeconds - (elapsedServerMs + Math.max(0, elapsedLocalMs)) / 1000));
}
