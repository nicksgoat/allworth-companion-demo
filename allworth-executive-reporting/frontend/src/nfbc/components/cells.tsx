// Controlled, lightweight editable cells (no grid library, no contenteditable).

import { useEffect, useState } from 'react';

const fmtMoney = (n: number | null): string =>
  n == null ? '' : n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 });

interface MoneyCellProps {
  value: number | null;
  disabled?: boolean;
  onCommit: (n: number) => void;
}

/** Money input: raw digits on focus, $-formatted on blur, commit on blur/Enter. */
export function MoneyCell({ value, disabled, onCommit }: MoneyCellProps) {
  const [editing, setEditing] = useState(false);
  const [raw, setRaw] = useState<string>('');

  useEffect(() => {
    if (!editing) setRaw(value == null ? '' : String(value));
  }, [value, editing]);

  const commit = () => {
    setEditing(false);
    const parsed = parseFloat(raw.replace(/[^0-9.-]/g, ''));
    if (!Number.isNaN(parsed) && parsed !== value) onCommit(parsed);
  };

  return (
    <input
      className="nfbc-cell nfbc-money"
      disabled={disabled}
      value={editing ? raw : fmtMoney(value)}
      onFocus={() => { setEditing(true); setRaw(value == null ? '' : String(value)); }}
      onChange={(e) => setRaw(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
        if (e.key === 'Escape') { setEditing(false); setRaw(value == null ? '' : String(value)); }
      }}
      inputMode="decimal"
    />
  );
}

interface TextCellProps {
  value: string | null;
  disabled?: boolean;
  placeholder?: string;
  onCommit: (s: string) => void;
}

export function TextCell({ value, disabled, placeholder, onCommit }: TextCellProps) {
  const [draft, setDraft] = useState(value ?? '');
  useEffect(() => setDraft(value ?? ''), [value]);
  const commit = () => { if (draft !== (value ?? '')) onCommit(draft); };
  return (
    <input
      className="nfbc-cell"
      disabled={disabled}
      value={draft}
      placeholder={placeholder}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
        if (e.key === 'Escape') setDraft(value ?? '');
      }}
    />
  );
}

interface SelectCellProps {
  value: string;
  options: string[];
  disabled?: boolean;
  onCommit: (s: string) => void;
}

export function SelectCell({ value, options, disabled, onCommit }: SelectCellProps) {
  const opts = options.includes(value) ? options : [value, ...options];
  return (
    <select
      className="nfbc-cell nfbc-select"
      disabled={disabled}
      value={value}
      onChange={(e) => onCommit(e.target.value)}
    >
      {opts.map((o) => (
        <option key={o} value={o}>{o}</option>
      ))}
    </select>
  );
}
