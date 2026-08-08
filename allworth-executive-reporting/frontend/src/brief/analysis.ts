// Analysis service. In mock mode this returns pre-built structured analyses;
// live mode will call POST /brief/api/analyze (Claude, server-side, with the
// email treated as untrusted input). All output — mock or live — passes
// through parseAnalysis() before rendering. A null return means "analysis
// unavailable": the UI shows a safe fallback and always keeps the original
// email accessible.

import type { EmailAnalysis, ExecutiveEmail } from './types';
import { MOCK_ANALYSES } from './mockData';
import { parseAnalysis } from './validate';

export function getAnalysis(email: ExecutiveEmail): EmailAnalysis | null {
  const raw = MOCK_ANALYSES[email.id];
  if (!raw) return null;
  return parseAnalysis(raw);
}

export function fallbackAnalysisNotice(): string {
  return 'AI analysis is unavailable for this email. The full original message is shown below — nothing has been hidden.';
}
