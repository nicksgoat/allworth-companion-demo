// src/components/CrmFlyout.tsx
// Reusable right-side slide-in panel — the Wealthbox-style record flyout.
// Renders a labeled field stack for a selected opportunity, activity, or any
// record. Purely presentational: the parent controls open state and content.

import { useEffect, useRef } from 'react';
import './CrmFlyout.css';

export interface FlyoutField {
  label: string;
  value: React.ReactNode;
}

interface CrmFlyoutProps {
  open: boolean;
  kicker?: string;
  title: string;
  fields: FlyoutField[];
  linkHref?: string;
  linkLabel?: string;
  onClose: () => void;
}

const CrmFlyout = ({ open, kicker, title, fields, linkHref, linkLabel, onClose }: CrmFlyoutProps) => {
  const closeRef = useRef<HTMLButtonElement>(null);
  const restoreRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    // Move focus into the dialog and give it back on close.
    restoreRef.current = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      restoreRef.current?.focus?.();
    };
  }, [open, onClose]);

  return (
    <div className={`crm-flyout-root${open ? ' open' : ''}`} aria-hidden={!open}>
      <div className="crm-flyout-scrim" onClick={onClose} />
      <aside className="crm-flyout" role="dialog" aria-modal="true" aria-label={title}>
        <div className="crm-flyout-head">
          <div>
            {kicker && <div className="crm-flyout-kicker">{kicker}</div>}
            <h3 className="crm-flyout-title">{title}</h3>
          </div>
          <button ref={closeRef} type="button" className="crm-flyout-close" onClick={onClose} aria-label="Close">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M18 6 6 18" /><path d="m6 6 12 12" /></svg>
          </button>
        </div>
        <div className="crm-flyout-body">
          {fields.map((f) => (
            <div key={f.label} className="crm-flyout-field">
              <div className="crm-flyout-label">{f.label}</div>
              <div className="crm-flyout-value">{f.value ?? '—'}</div>
            </div>
          ))}
        </div>
        {linkHref && (
          <div className="crm-flyout-foot">
            <a className="crm-flyout-link" href={linkHref} target="_blank" rel="noreferrer">
              {linkLabel ?? 'Open in Salesforce'}
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M7 17 17 7" /><path d="M8 7h9v9" /></svg>
            </a>
          </div>
        )}
      </aside>
    </div>
  );
};

export default CrmFlyout;
