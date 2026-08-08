// Executive Brief — shared types. Mirrors the schema in the build brief so the
// mock analysis payloads and the future Claude-backed /brief/api/analyze
// endpoint speak the same shape.

export type Priority = 'critical' | 'high' | 'medium' | 'low';

export type Category =
  | 'needs_decision'
  | 'needs_response'
  | 'important'
  | 'waiting'
  | 'delegatable'
  | 'low_priority';

export type ExecutiveEmail = {
  id: string;
  threadId: string;
  senderName: string;
  senderEmail: string;
  senderRole?: string;
  subject: string;
  receivedAt: string;
  priority: Priority;
  category: Category;
  summary: string;
  request: string;
  deadline?: string;
  recommendedAction: string;
  confidence: number;
  attachmentCount: number;
  unread: boolean;
  completed: boolean;
  snoozedUntil?: string;
  delegatedTo?: string;
};

export type ThreadMessage = {
  id: string;
  from: string;
  fromEmail: string;
  sentAt: string;
  body: string;
};

export type EmailThread = {
  threadId: string;
  subject: string;
  messages: ThreadMessage[];
};

export const CATEGORY_LABELS: Record<Category, string> = {
  needs_decision: 'Needs your decision',
  needs_response: 'Needs your response',
  important: 'Important to know',
  waiting: 'Waiting on someone',
  delegatable: 'Can be delegated',
  low_priority: 'Low priority',
};

export type KeyPerson = {
  name: string;
  role?: string;
};

export type AnalyzedAttachment = {
  name: string;
  needs_review: boolean;
};

export type ReplyIntent =
  | 'approve'
  | 'decline'
  | 'ask_question'
  | 'delegate'
  | 'acknowledge'
  | 'schedule'
  | 'provide_decision'
  | 'custom';

export type EmailAnalysis = {
  category: Category;
  priority: Priority;
  summary: string;
  request: string;
  recommended_action: string;
  why_it_matters: string;
  deadline?: string;
  risks: string[];
  missing_context: string[];
  key_people: KeyPerson[];
  commitments: string[];
  attachments: AnalyzedAttachment[];
  suggested_reply_intents: ReplyIntent[];
  confidence: number;
};

export type Tone = 'concise' | 'direct' | 'warm' | 'executive' | 'detailed';

export const REPLY_INTENT_LABELS: Record<ReplyIntent, string> = {
  approve: 'Approve',
  decline: 'Decline',
  ask_question: 'Ask a question',
  delegate: 'Delegate',
  acknowledge: 'Acknowledge',
  schedule: 'Schedule a meeting',
  provide_decision: 'Provide a decision',
  custom: 'Custom response',
};

export const TONE_LABELS: Record<Tone, string> = {
  concise: 'Concise',
  direct: 'Direct',
  warm: 'Warm',
  executive: 'Executive',
  detailed: 'Detailed',
};
