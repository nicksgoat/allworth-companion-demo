import type { EmailAnalysis, ReplyIntent, Tone } from "./types";
import type { ExecutiveEmail } from "./types";

/**
 * Mock reply generator. Deterministic templates keyed by intent and tone so the
 * full flow is demonstrable offline. Later this becomes a server-side call to
 * Claude (POST /api/emails/:id/draft-reply); the email body is untrusted input
 * and must never be treated as instructions.
 */

const firstName = (full: string) => full.split(" ")[0];

function opening(email: ExecutiveEmail, tone: Tone): string {
  const name = firstName(email.senderName);
  switch (tone) {
    case "warm":
      return `Hi ${name},\n\nThanks for laying this out so clearly.`;
    case "concise":
    case "direct":
      return `${name} —`;
    case "executive":
      return `${name},`;
    case "detailed":
      return `Hi ${name},\n\nI've read through this in full.`;
  }
}

function closing(tone: Tone): string {
  switch (tone) {
    case "warm":
      return "\n\nThanks again for staying on top of this.";
    case "concise":
      return "";
    case "direct":
      return "";
    case "executive":
      return "\n\nKeep me posted.";
    case "detailed":
      return "\n\nLet me know if any of this needs discussion.";
  }
}

function core(intent: ReplyIntent, email: ExecutiveEmail, analysis: EmailAnalysis | null): string {
  const req = analysis?.request ?? email.request;
  switch (intent) {
    case "approve":
      return `Approved — go ahead. One condition: ${analysis?.risks[0] ? `please address this first: ${analysis.risks[0]}` : "confirm the details we discussed stand."}`;
    case "decline":
      return `I'm not going to approve this as proposed. ${analysis?.risks[0] ?? "The current terms don't work for me."} Come back with a revised version and I'll take another look.`;
    case "ask_question":
      return `Before I respond on "${req}" — ${analysis?.missing_context[0] ? `can you clarify one thing first: ${analysis.missing_context[0]}` : "can you give me the underlying detail behind this?"}`;
    case "delegate":
      return `I'm going to hand this to a member of my team to take forward — they'll pick it up directly with you and have my full support on it.`;
    case "acknowledge":
      return `Received and understood. No response needed from you — I have what I need.`;
    case "schedule":
      return `Rather than resolve this over email, let's talk. My assistant will send over a couple of times — 30 minutes should do it.`;
    case "provide_decision":
      return `Here's my decision: proceed as outlined, with one adjustment we should discuss. ${analysis?.recommended_action ?? ""}`;
    case "custom":
      return `(Write your reply here.)`;
  }
}

export function generateReply(
  email: ExecutiveEmail,
  analysis: EmailAnalysis | null,
  intent: ReplyIntent,
  tone: Tone
): string {
  const body = core(intent, email, analysis);
  if (tone === "concise") {
    // Strip to the essential sentence(s).
    return `${opening(email, tone)} ${body}`;
  }
  return `${opening(email, tone)}\n\n${body}${closing(tone)}`;
}

export type Refinement = "shorter" | "warmer" | "more_direct" | "add_context";

export function refineReply(current: string, refinement: Refinement, email: ExecutiveEmail, analysis: EmailAnalysis | null): string {
  switch (refinement) {
    case "shorter": {
      const sentences = current.replace(/\n+/g, " ").split(/(?<=[.?!])\s+/).filter(Boolean);
      return sentences.slice(0, Math.max(1, Math.ceil(sentences.length / 2))).join(" ");
    }
    case "warmer":
      return `Hi ${email.senderName.split(" ")[0]},\n\nI appreciate you bringing this to me directly.\n\n${current.replace(/^.*?—\s*/s, "").replace(/^Hi .*?,\n\n/s, "")}\n\nThanks for the great work on this.`;
    case "more_direct": {
      const stripped = current
        .replace(/^Hi .*?,\n\n/s, "")
        .replace(/Thanks for laying this out so clearly\.\s*/g, "")
        .replace(/\n\nThanks again for staying on top of this\.?/g, "")
        .replace(/\n\nLet me know if any of this needs discussion\.?/g, "");
      return stripped.trim();
    }
    case "add_context": {
      const context = analysis?.commitments[0] ?? analysis?.why_it_matters ?? email.summary;
      return `${current}\n\nFor context: ${context}`;
    }
  }
}
