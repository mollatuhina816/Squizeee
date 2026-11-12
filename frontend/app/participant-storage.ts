// Browser credentials identify an existing attempt; quiz progress stays on the server.
export type SavedParticipant = {
  session_id: string; participant_id: string; token: string; code: string; classLevel?: string; email?: string;
};
const key = 'quizeee-participant';
const prefix = 'quizeee-participant:';
function availableStorage(): Storage[] {
  const stores: Storage[] = [];
  for (const name of ['localStorage', 'sessionStorage'] as const) {
    try { stores.push(window[name]); } catch { /* Browser privacy settings. */ }
  }
  return stores;
}
function read(storage: Storage, name: string): SavedParticipant | null {
  try {
    const value = JSON.parse(storage.getItem(name) || 'null');
    return value && ['session_id', 'participant_id', 'token', 'code'].every(
      field => typeof value[field] === 'string' && value[field].length > 0
    ) ? value : null;
  } catch { return null; }
}
export function saveParticipant(value: SavedParticipant): void {
  // Keep tab storage as a fallback when persistent storage is unavailable.
  for (const storage of availableStorage()) {
    try {
      for (const alias of [value.code, value.session_id, value.participant_id]) {
        storage.setItem(prefix + alias, JSON.stringify(value));
        if(value.email)storage.setItem(prefix + alias + ':email:' + value.email.trim().toLowerCase(), JSON.stringify(value));
        storage.setItem('quizeee-quiz-token:' + alias, value.token);
      }
      storage.setItem(key, JSON.stringify(value));
    } catch { /* Restricted browser storage must not interrupt participation. */ }
  }
}
export function loadParticipant(code = '', email?: string): SavedParticipant | null {
  const requested = code.trim();
  for (const storage of availableStorage()) {
    const value = (requested && email ? read(storage, prefix + requested + ':email:' + email.trim().toLowerCase()) : null) || (requested ? read(storage, prefix + requested) : null) || read(storage, key);
    if (value && (email === undefined || value.email?.trim().toLowerCase() === email.trim().toLowerCase()) && (!requested || requested === value.code || requested === value.session_id || requested === value.participant_id)) {
      saveParticipant(value); // Migrate existing tab-scoped credentials.
      return value;
    }
  }
  return null;
}
