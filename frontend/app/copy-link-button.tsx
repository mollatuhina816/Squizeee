'use client';

import { useState } from 'react';

export default function CopyLinkButton({ url }: { url: string }) {
  const [copiedUrl, setCopiedUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function copy() {
    setBusy(true);
    setError('');
    setCopiedUrl('');
    try {
      await navigator.clipboard.writeText(url);
      setCopiedUrl(url);
    } catch {
      setError('Could not copy. Right-click the participant link and choose Copy link address.');
    } finally {
      setBusy(false);
    }
  }

  return <span>
    <button type="button" className="secondary" disabled={!url || busy} onClick={copy}>
      {busy ? 'Copying...' : copiedUrl === url && url ? 'Copied!' : 'Copy link'}
    </button>
    <span role="status">{copiedUrl === url && url ? ' Link copied to clipboard.' : ''}</span>
    {error && <span role="alert"> {error}</span>}
  </span>;
}
