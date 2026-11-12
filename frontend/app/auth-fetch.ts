'use client';

let renewal: Promise<boolean> | null = null;

async function renewSession(): Promise<boolean> {
  const renew = async () => {
    // Another request or tab may already have renewed the shared cookie.
    const current = await fetch('/api/v1/auth/me', { credentials: 'include', cache: 'no-store' });
    if (current.ok) return true;
    if (current.status !== 401) return false;
    const response = await fetch('/api/v1/auth/refresh', { method: 'POST', credentials: 'include' });
    return response.ok;
  };
  // Refresh tokens are single-use, so coordinate rotation across browser tabs.
  if (typeof navigator !== 'undefined' && navigator.locks) {
    return navigator.locks.request('quizeee-session-renewal', renew);
  }
  return renew();
}

/** Authenticated app calls only; participant credentials use their own flow. */
export async function authFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const response = await fetch(input, init);
  const url = typeof input === 'string' ? input : input instanceof URL ? input.pathname : input.url;
  if (response.status !== 401 || /\/auth\/(login|register|logout|refresh)(?:[?#]|$)/.test(url)) return response;
  if (!renewal) {
    renewal = renewSession().catch(() => false).finally(() => { renewal = null; });
  }
  if (!await renewal) return response;
  // A 401 is rejected before the protected action executes; retry only once.
  return fetch(input, init);
}
