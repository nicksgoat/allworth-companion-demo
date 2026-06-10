import { defaultHousehold, defaultPortfolio } from "./lib/planningLogic.mjs";

export type ChatMessage = {
  role: "user" | "assistant" | "system";
  content: string;
};

export type MetricCard = {
  label: string;
  value: string;
  tone: "good" | "warning" | "danger" | "neutral";
  detail?: string;
};

export type AdvisorAction = {
  title: string;
  priority: "high" | "medium" | "low";
  rationale: string;
};

export type ToolResult = {
  tool: string;
  summary: string;
  cards: MetricCard[];
  actions: AdvisorAction[];
  data: Record<string, unknown>;
  disclaimers: string[];
};

export type ChatResponse = {
  answer: string;
  intent: string;
  result: ToolResult;
  suggested_prompts: string[];
};

const API_URL = process.env.EXPO_PUBLIC_API_URL || "http://127.0.0.1:8000";

export async function sendChat(messages: ChatMessage[], household = defaultHousehold, portfolio = defaultPortfolio): Promise<ChatResponse> {
  const response = await fetch(`${API_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, household, portfolio })
  });
  if (!response.ok) {
    throw new Error(`Chat failed: ${response.status}`);
  }
  return response.json();
}

export async function runPortfolioReview(portfolio = defaultPortfolio): Promise<ToolResult> {
  const response = await fetch(`${API_URL}/api/tools/portfolio/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ analysis: "portfolio_review", portfolio })
  });
  if (!response.ok) {
    throw new Error(`Portfolio review failed: ${response.status}`);
  }
  return response.json();
}

