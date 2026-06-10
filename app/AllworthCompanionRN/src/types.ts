export interface ClientPersona {
  id: string;
  name: string;
  age: number;
  city: string;
  advisorId: string;
  bio: string;
  avatarInitials: string;
}

export interface Advisor {
  id: string;
  name: string;
  title: string;
  avatarInitials: string;
}

export interface Account {
  id: string;
  name: string;
  institution: string;
  group: string;
  type: string;
  balance: number;
  history?: number[];
}

export interface MonthValue {
  month: string;
  value: number;
}

export interface Nudge {
  id: string;
  type: string;
  title: string;
  headline: string;
  body: string;
  cta: string;
  advisorCta: string;
  severity: string;
}

export interface LiquidityEvent {
  label: string;
  amount: number;
  deadline: string;
  note: string;
}

export interface Dashboard {
  client: ClientPersona | null;
  advisor: Advisor;
  netWorth: number;
  netWorthHistory: MonthValue[];
  allworthTotal: number;
  heldAwayTotal: number;
  liabilitiesTotal: number;
  accounts: { allworth: Account[]; outside: Account[] };
  spending: { avg3mo: number; plan: number; overPlanPct: number };
  nudges: Nudge[];
  liquidityEvent: LiquidityEvent;
  disclaimer: string;
}

export interface SpendingMonth {
  month: string;
  total: number;
  planned: number;
  categories: Record<string, number>;
}

export interface SpendingDetail {
  months: SpendingMonth[];
  all: SpendingMonth[];
  avg3mo: number;
  plan: number;
  overPlanPct: number;
}

export interface LearnedFact {
  fact: string;
  category: string;
  source_quote: string;
  learned_at: string;
  confidence: number;
  status: string;
}

export interface ProfileResponse {
  clientId: string;
  facts: LearnedFact[];
}

export interface ProactiveResponse {
  message: string;
}

export interface Household {
  clientId: string;
  name: string;
  managedAssets: number;
  heldAwayDetected: number;
  openNudges: number;
  lastContact: string;
  highlight?: boolean;
}

export interface BookResponse {
  advisor: Advisor;
  households: Household[];
}

export interface AdvisorBrief {
  client: ClientPersona | null;
  managedTotal: number;
  heldAwayDetected: number;
  heldAwayAccounts: Account[];
  liabilities: Account[];
  openNudges: Nudge[];
  profile: LearnedFact[];
  liquidityEvent: LiquidityEvent;
  narrative: string;
}

// Chat

export interface ToolChip {
  name: string;
  label: string;
  running: boolean;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  chips: ToolChip[];
  sources: string[];
  isStreaming: boolean;
}

export type ChatEvent =
  | { kind: "tool_start"; name: string; label: string }
  | { kind: "tool_end"; name: string }
  | { kind: "text"; delta: string }
  | { kind: "done"; sources: string[]; fallback: boolean }
  | { kind: "error"; message: string };
