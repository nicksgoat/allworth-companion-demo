// src/services/timezone.ts
// Shared timezone utilities for pipeline views.

import { useCallback, useEffect, useState } from 'react';

export type TzKey = 'eastern' | 'central' | 'pacific';

export interface TzOption {
  key: TzKey;
  label: string;
  iana: string;
  short: string;
}

export const TZ_OPTIONS: TzOption[] = [
  { key: 'eastern', label: 'Eastern', iana: 'America/New_York', short: 'ET' },
  { key: 'central', label: 'Central', iana: 'America/Chicago', short: 'CT' },
  { key: 'pacific', label: 'Pacific', iana: 'America/Los_Angeles', short: 'PT' },
];

const DEFAULT_STORAGE_KEY = 'pipeline.tz';
const DEFAULT_TZ: TzKey = 'eastern';

const isTzKey = (v: unknown): v is TzKey =>
  v === 'eastern' || v === 'central' || v === 'pacific';

const getTzFromStorage = (storageKey: string, fallback: TzKey): TzKey => {
  try {
    const v = window.localStorage.getItem(storageKey);
    if (isTzKey(v)) return v;
  } catch {
    /* ignore */
  }
  return fallback;
};

export interface UseTimezoneOptions {
  /** Zone used when nothing is stored yet (defaults to Eastern). */
  defaultTz?: TzKey;
  /** localStorage key. Each page can keep an independent preference by passing
   *  its own key; pages sharing a key stay in sync (see the cross-tab handler). */
  storageKey?: string;
}

export const useTimezone = (
  options: UseTimezoneOptions = {}
): [TzKey, (next: TzKey) => void, TzOption] => {
  const { defaultTz = DEFAULT_TZ, storageKey = DEFAULT_STORAGE_KEY } = options;
  const [tz, setTzState] = useState<TzKey>(() => getTzFromStorage(storageKey, defaultTz));

  const setTz = useCallback(
    (next: TzKey) => {
      setTzState(next);
      try {
        window.localStorage.setItem(storageKey, next);
      } catch {
        /* ignore */
      }
    },
    [storageKey]
  );

  // Cross-tab / other-page sync for consumers sharing this storage key.
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key !== storageKey) return;
      if (isTzKey(e.newValue)) setTzState(e.newValue);
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, [storageKey]);

  const option = TZ_OPTIONS.find((o) => o.key === tz) ?? TZ_OPTIONS[0];
  return [tz, setTz, option];
};

export const getTzIana = (tz: TzKey): string =>
  TZ_OPTIONS.find((o) => o.key === tz)?.iana ?? 'America/New_York';

/** Format an epoch ms as "9:57 AM" in the selected zone. */
export const formatClockInTz = (ms: number, tz: TzKey): string => {
  const d = new Date(ms);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleTimeString([], {
    hour: 'numeric',
    minute: '2-digit',
    timeZone: getTzIana(tz),
  });
};

/** Return the YYYY-MM-DD date-string for a value as seen in the given zone. */
export const dayKeyInTz = (
  v: string | number | Date | null | undefined,
  tz: TzKey
): string | null => {
  if (v == null) return null;
  const d = v instanceof Date ? v : new Date(v);
  if (Number.isNaN(d.getTime())) return null;
  // 'en-CA' gives ISO-like YYYY-MM-DD output
  return d.toLocaleDateString('en-CA', { timeZone: getTzIana(tz) });
};

/** True if `iso` falls on the same calendar day as `ref` in the selected zone. */
export const sameDayInTz = (
  iso: string | null | undefined,
  ref: Date,
  tz: TzKey
): boolean => {
  if (!iso) return false;
  const a = dayKeyInTz(iso, tz);
  const b = dayKeyInTz(ref, tz);
  return !!a && a === b;
};
