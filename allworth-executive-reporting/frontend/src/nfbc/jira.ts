// Jira ticket linking helpers for the NFBC console.

const JIRA_BASE = 'https://allworthfinancial.atlassian.net';

// A real Jira issue key looks like "AI-7141" / "AR-1234".
const KEY_RE = /^[A-Z][A-Z0-9]+-\d+$/;

export function isJiraKey(key: string | null | undefined): boolean {
  return !!key && KEY_RE.test(key.trim());
}

export function jiraTicketUrl(key: string): string {
  return `${JIRA_BASE}/browse/${encodeURIComponent(key.trim())}`;
}
