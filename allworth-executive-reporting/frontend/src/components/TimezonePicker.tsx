// src/components/TimezonePicker.tsx
// Shared timezone <select>. Renders the TZ_OPTIONS list and reports the picked
// key back to the caller. Structure + chrome live in TimezonePicker.css and are
// themeable via --tz-* custom properties (defaults match the dark pipeline
// theme; the App Usage glass theme overrides them under .usage-console).

import { TZ_OPTIONS, type TzKey } from '../services/timezone';
import './TimezonePicker.css';

interface TimezonePickerProps {
  value: TzKey;
  onChange: (tz: TzKey) => void;
  className?: string;
  ariaLabel?: string;
}

export default function TimezonePicker({
  value,
  onChange,
  className,
  ariaLabel = 'Display timezone',
}: TimezonePickerProps) {
  return (
    <select
      className={'tz-select' + (className ? ` ${className}` : '')}
      value={value}
      onChange={(e) => onChange(e.target.value as TzKey)}
      aria-label={ariaLabel}
    >
      {TZ_OPTIONS.map((o) => (
        <option key={o.key} value={o.key}>
          {o.label} ({o.short})
        </option>
      ))}
    </select>
  );
}
