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

export interface CashFlow {
  date: string;
  amount: number;
  month?: string;
  source?: string;
  label?: string;
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
  performanceCashFlows?: CashFlow[];
  performance?: {
    netWorth?: {
      method: string;
      return: number;
      ratio: number;
      return_pct: number;
      gain_loss: number;
      inflow: number;
      outflow: number;
      net_cash_flow: number;
      weighted_cash_flow: number;
    } | null;
  };
  allworthTotal: number;
  heldAwayTotal: number;
  liabilitiesTotal: number;
  accounts: { allworth: Account[]; outside: Account[] };
  spending: { avg3mo: number; plan: number; overPlanPct: number };
  nudges: Nudge[];
  liquidityEvent: LiquidityEvent;
  dataStatus?: {
    mode: string;
    label: string;
    generatedAt: string;
    asOf: string;
    isSynthetic: boolean;
    isStale: boolean;
  };
  disclaimer: string;
}

export type AssetClass = "us_equity" | "intl_equity" | "bond" | "muni_bond" | "cash";

export interface Position {
  accountId: string;
  symbol: string;
  name: string;
  qty: number;
  price: number;
  value: number;
  assetClass: AssetClass;
  averageCostBasis?: number;
  costBasis?: number;
  unrealizedGain?: number;
  longTermValue?: number;
  longTermCostBasis?: number;
  longTermUnrealizedGain?: number;
  shortTermValue?: number;
  shortTermCostBasis?: number;
  shortTermUnrealizedGain?: number;
}

export interface Portfolio {
  positions: Position[];
  byAccount: Record<string, Position[]>;
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
  id: string;
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

export interface MeetingNote {
  id: string;
  date: string;
  title: string;
  summary: string;
  advisor: string;
  attendees?: string[];
}

export interface MeetingNotesResponse {
  clientId: string;
  notes: MeetingNote[];
}

export interface ProactiveResponse {
  message: string;
  suggested?: string[];
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
  reviewWorkflow?: {
    status: string;
    summary: string;
    decisionsToReview: { id: string; label: string; whyItMatters: string }[];
    talkingPoints: string[];
    openQuestions: string[];
    nextBestAction: string;
  };
}

// Chat

export interface ToolChip {
  name: string;
  label: string;
  running: boolean;
}

// A tool whose structured result the chat renders as a rich inline widget
// (the rebalancer + the Monte Carlo projection).
export interface ToolWidget {
  name: string;
  result: any;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "advisor";
  text: string;
  // Set on advisor interjections — who posted into the thread.
  advisorName?: string;
  chips: ToolChip[];
  sources: string[];
  isStreaming: boolean;
  suggested?: string[];
  widgets?: ToolWidget[];
  feedback?: "positive" | "negative";
  quality?: {
    vision_score?: number;
    safety_flags?: string[];
    missing?: string[];
  };
}

// One entry of the server-stored thread (GET /api/clients/{id}/conversation).
// Advisor interjections carry an id (poll cursor) + attribution; user/assistant
// turns are id-less store records.
export interface ConversationMessage {
  seq: number;
  id: string | null;
  role: "user" | "assistant" | "advisor";
  text: string;
  advisorId?: string;
  advisorName?: string;
  ts?: string | null;
}

export type ChatEvent =
  | { kind: "tool_start"; name: string; label: string }
  | { kind: "tool_end"; name: string; result?: any }
  | { kind: "text"; delta: string }
  | { kind: "done"; sources: string[]; suggested: string[]; quality?: ChatMessage["quality"] }
  | { kind: "error"; message: string };
