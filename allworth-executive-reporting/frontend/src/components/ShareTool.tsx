// src/components/ShareTool.tsx
// Drop-in "Share" affordance for any tool page. Renders a share button + popover
// ONLY for users who are allowed to share this tool (resolved via access.ts —
// a per-tool "share" grant, membership in a group that shares it, or all-access
// admins). A sharer can grant this tool's view access to another user (picked
// from the roster or typed as an email) and revoke grants they made.
//
// Usage:  <ShareTool toolId="repcodes" toolName="Rep Codes" />

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { adminApi, type ShareRecipient } from '../services/admin';
import { canShareTool, useEffectiveAccess } from '../services/access';
import './ShareTool.css';

interface ShareToolProps {
  toolId: string;
  toolName: string;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function ShareTool({ toolId, toolName }: ShareToolProps) {
  const access = useEffectiveAccess();
  const canShare = canShareTool(access, toolId);

  const [open, setOpen] = useState(false);
  const [recipients, setRecipients] = useState<ShareRecipient[]>([]);
  const [roster, setRoster] = useState<string[]>([]);
  const [query, setQuery] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const info = await adminApi.getShareRecipients(toolId);
      setRecipients(info.recipients);
      setRoster(info.roster);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [toolId]);

  useEffect(() => {
    if (open && canShare) void load();
  }, [open, canShare, load]);

  // Dismiss on outside click or Escape.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const recipientSet = useMemo(() => new Set(recipients.map((r) => r.email)), [recipients]);
  const q = query.trim().toLowerCase();
  const suggestions = useMemo(
    () => roster.filter((e) => !recipientSet.has(e) && e.includes(q)).slice(0, 6),
    [roster, recipientSet, q]
  );
  const canGrant = EMAIL_RE.test(q) && !recipientSet.has(q);

  const grant = async (email: string) => {
    const e = email.trim().toLowerCase();
    if (!e || busy) return;
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      await adminApi.shareTool(toolId, e);
      setQuery('');
      setNote(`Shared ${toolName} with ${e}`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (email: string) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      await adminApi.revokeShare(toolId, email);
      setNote(`Removed ${toolName} access for ${email}`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'Enter') return;
    if (suggestions.length > 0) void grant(suggestions[0]);
    else if (canGrant) void grant(q);
  };

  // The button is always visible; users without share rights (or an active
  // "view as" impersonation, which never carries share rights) see a message
  // explaining they can't share, rather than the button being hidden.
  const direct = recipients.filter((r) => r.direct);
  const inherited = recipients.filter((r) => !r.direct);

  return (
    <div className="sharetool" ref={wrapRef}>
      <button
        type="button"
        className={'sharetool-btn' + (open ? ' active' : '')}
        onClick={() => setOpen((o) => !o)}
        title={`Share ${toolName} with other users`}
        aria-haspopup="dialog"
        aria-expanded={open}
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="18" cy="5" r="3" />
          <circle cx="6" cy="12" r="3" />
          <circle cx="18" cy="19" r="3" />
          <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
          <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
        </svg>
        Share
      </button>

      {open && (
        <div className="sharetool-pop" role="dialog" aria-label={`Share ${toolName}`}>
          <div className="sharetool-head">
            <strong>Share {toolName}</strong>
            <span className="sharetool-sub">Grant access to other users</span>
          </div>

          {!canShare ? (
            <div className="sharetool-noaccess">You do not have access to share this page</div>
          ) : (
            <>
              <div className="sharetool-add">
                <input
                  type="text"
                  value={query}
                  placeholder="Pick a user or type an email…"
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={onKeyDown}
                  autoFocus
                />
                <button
                  type="button"
                  className="sharetool-grant"
                  disabled={busy || (!canGrant && suggestions.length === 0)}
                  onClick={() => grant(suggestions.length > 0 ? suggestions[0] : q)}
                >
                  Share
                </button>
              </div>

              {q && (suggestions.length > 0 || canGrant) && (
                <div className="sharetool-suggest">
                  {suggestions.map((e) => (
                    <button key={e} type="button" className="sharetool-suggest-item" onClick={() => grant(e)}>
                      {e}
                    </button>
                  ))}
                  {canGrant && (
                    <button type="button" className="sharetool-suggest-item new" onClick={() => grant(q)}>
                      Share with new user “{q}”
                    </button>
                  )}
                </div>
              )}

              {error && <div className="sharetool-msg err">{error}</div>}
              {note && !error && <div className="sharetool-msg ok">{note}</div>}

              <div className="sharetool-list-label">People with access</div>
              {direct.length === 0 && inherited.length === 0 ? (
                <div className="sharetool-empty">No one has been given access yet.</div>
              ) : (
                <ul className="sharetool-list">
                  {direct.map((r) => (
                    <li key={r.email} className="sharetool-row">
                      <span className="sharetool-email">{r.email}</span>
                      <button
                        type="button"
                        className="sharetool-remove"
                        onClick={() => revoke(r.email)}
                        disabled={busy}
                        title="Remove access"
                      >
                        ×
                      </button>
                    </li>
                  ))}
                  {inherited.map((r) => (
                    <li key={r.email} className="sharetool-row muted">
                      <span className="sharetool-email">{r.email}</span>
                      <span className="sharetool-tag" title={`Via group: ${r.inherited_from.join(', ')}`}>
                        group
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
