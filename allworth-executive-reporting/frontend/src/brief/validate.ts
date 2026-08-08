// Runtime validation for AI-produced analysis payloads. Dependency-free (the
// portal frontend does not carry zod); the checks mirror the schema in
// types.ts. All analysis output — mock today, Claude tomorrow — passes through
// parseAnalysis() before rendering. A null return means "analysis
// unavailable": the UI must show the safe fallback and always keep the
// original email accessible.

import type { Category, EmailAnalysis, Priority, ReplyIntent } from './types';

const PRIORITIES: readonly string[] = ['critical', 'high', 'medium', 'low'];
const CATEGORIES: readonly string[] = [
  'needs_decision',
  'needs_response',
  'important',
  'waiting',
  'delegatable',
  'low_priority',
];
const INTENTS: readonly string[] = [
  'approve',
  'decline',
  'ask_question',
  'delegate',
  'acknowledge',
  'schedule',
  'provide_decision',
  'custom',
];

function isNonEmptyString(v: unknown): v is string {
  return typeof v === 'string' && v.length > 0;
}

function isStringArray(v: unknown): v is string[] {
  return Array.isArray(v) && v.every((s) => typeof s === 'string');
}

export function parseAnalysis(input: unknown): EmailAnalysis | null {
  if (typeof input !== 'object' || input === null) return null;
  const o = input as Record<string, unknown>;

  if (!CATEGORIES.includes(o.category as string)) return null;
  if (!PRIORITIES.includes(o.priority as string)) return null;
  if (!isNonEmptyString(o.summary)) return null;
  if (!isNonEmptyString(o.request)) return null;
  if (!isNonEmptyString(o.recommended_action)) return null;
  if (!isNonEmptyString(o.why_it_matters)) return null;
  if (o.deadline !== undefined && typeof o.deadline !== 'string') return null;
  if (!isStringArray(o.risks)) return null;
  if (!isStringArray(o.missing_context)) return null;
  if (!isStringArray(o.commitments)) return null;
  if (
    !Array.isArray(o.key_people) ||
    !o.key_people.every(
      (p) =>
        typeof p === 'object' &&
        p !== null &&
        typeof (p as Record<string, unknown>).name === 'string' &&
        ((p as Record<string, unknown>).role === undefined ||
          typeof (p as Record<string, unknown>).role === 'string'),
    )
  ) {
    return null;
  }
  if (
    !Array.isArray(o.attachments) ||
    !o.attachments.every(
      (a) =>
        typeof a === 'object' &&
        a !== null &&
        typeof (a as Record<string, unknown>).name === 'string' &&
        typeof (a as Record<string, unknown>).needs_review === 'boolean',
    )
  ) {
    return null;
  }
  if (
    !Array.isArray(o.suggested_reply_intents) ||
    !o.suggested_reply_intents.every((i) => INTENTS.includes(i as string))
  ) {
    return null;
  }
  if (typeof o.confidence !== 'number' || o.confidence < 0 || o.confidence > 1) return null;

  return {
    category: o.category as Category,
    priority: o.priority as Priority,
    summary: o.summary,
    request: o.request,
    recommended_action: o.recommended_action,
    why_it_matters: o.why_it_matters,
    deadline: o.deadline as string | undefined,
    risks: o.risks,
    missing_context: o.missing_context,
    key_people: o.key_people as EmailAnalysis['key_people'],
    commitments: o.commitments,
    attachments: o.attachments as EmailAnalysis['attachments'],
    suggested_reply_intents: o.suggested_reply_intents as ReplyIntent[],
    confidence: o.confidence,
  };
}
