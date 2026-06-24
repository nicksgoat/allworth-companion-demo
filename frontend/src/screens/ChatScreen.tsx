import { Ionicons } from "@expo/vector-icons";
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import type { NativeScrollEvent, NativeSyntheticEvent } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { ChatMessageView } from "../components/Chat";
import { DisclaimerFooter } from "../components/Rows";
import { useApp } from "../state";
import { card, colors, fonts, radius, space, text } from "../theme";
import type { ChatEvent, ChatMessage, Dashboard } from "../types";

let nextId = 1;
const newMessage = (m: Omit<ChatMessage, "id">): ChatMessage => ({ ...m, id: String(nextId++) });

const LEGACY_SUGGESTIONS = [
  "Am I on track for retirement?",
  "Can I afford a $50,000 car?",
  "What would rebalancing to 70/30 look like?",
];

const compactSuggestions = (items: string[], limit = 3): string[] => {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const item of items) {
    const text = item.trim().replace(/\s+/g, " ");
    const key = text.toLowerCase();
    if (!text || seen.has(key)) continue;
    seen.add(key);
    result.push(text);
    if (result.length >= limit) break;
  }
  return result;
};

const hasLegacySuggestions = (suggested: string[]): boolean =>
  suggested.length === LEGACY_SUGGESTIONS.length &&
  suggested.every((item, index) => item === LEGACY_SUGGESTIONS[index]);

const suggestionsFromDashboard = (dashboard: Dashboard | null): string[] => {
  const suggestions: string[] = [];
  for (const nudge of dashboard?.nudges ?? []) {
    if (nudge.type === "spending") {
      suggestions.push("How does this spending affect my plan?");
    } else if (nudge.type === "concentration") {
      const symbol = nudge.title.split(" ", 1)[0] || "that position";
      suggestions.push(`What are my options for ${symbol}?`);
    }
  }
  return suggestions;
};

const dynamicSuggestions = ({
  suggested,
  latestUserText,
  assistantText,
  sources,
  dashboard,
}: {
  suggested: string[];
  latestUserText: string;
  assistantText: string;
  sources: string[];
  dashboard: Dashboard | null;
}): string[] => {
  if (suggested.length > 0 && !hasLegacySuggestions(suggested))
    return compactSuggestions(suggested);

  const text = `${latestUserText} ${assistantText}`.toLowerCase();
  const candidates: string[] = [];
  if (text.includes("spending") || text.includes("budget") || text.includes("over plan")) {
    candidates.push(
      "What spending level keeps the plan on track?",
      "Which categories are driving the overage?",
      "How does this affect the lake house timeline?",
    );
  }
  if (text.includes("car") || text.includes("afford") || text.includes("purchase")) {
    candidates.push(
      "What if I finance it instead?",
      "How would paying cash affect retirement odds?",
      "Which funding source creates the least tax drag?",
    );
  }
  if (text.includes("rebalance") || text.includes("allocation") || text.includes("70/30")) {
    candidates.push(
      "Show the tax impact in plain English",
      "Which holdings would be sold first?",
      "What if we limit realized gains?",
    );
  }
  if (sources.includes("Monte Carlo simulation")) {
    candidates.push("What improves the odds the most?", "How bad is the downside case?");
  }
  candidates.push(...suggestionsFromDashboard(dashboard));
  return compactSuggestions(candidates);
};

export function ChatScreen() {
  const app = useApp();
  const insets = useSafeAreaInsets();
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  // Id of the last assistant message that has finished typing in — follow-up
  // suggestion chips wait for this, so they don't pop in mid-reveal.
  const [revealedId, setRevealedId] = useState<string | null>(null);
  const handleRevealed = useCallback((id: string) => setRevealedId(id), []);
  const scrollRef = useRef<ScrollView>(null);
  // "Stick to bottom": follow a streaming answer only while you're already at
  // the bottom. The moment you scroll up to read, we stop following so the
  // text never yanks you back down mid-read.
  const pinnedToBottom = useRef(true);
  const lastCount = useRef(0);

  const loadProactive = async () => {
    if (app.chatMessages.length > 0) return;
    const clientFirstName = app.dashboard?.client?.name?.split(",")[0]?.split(" ")[0] ?? "there";
    let greeting = `Hi ${clientFirstName} — I can help you understand your accounts, spending, or plan. What's on your mind?`;
    let suggested: string[] = [];
    try {
      const res = await app.api.proactive(app.clientId, app.session);
      greeting = res.message;
      suggested = res.suggested ?? [];
    } catch {}
    app.setChatMessages((msgs) =>
      msgs.length > 0
        ? msgs
        : [
            newMessage({
              role: "assistant",
              text: greeting,
              chips: [],
              sources: [],
              isStreaming: false,
              suggested,
            }),
          ],
    );
  };

  useEffect(() => {
    loadProactive();
  }, [app.session]);

  // A prefilled prompt (from a nudge, a drill-in, or a quick action) auto-sends,
  // so every chat button is a real one-tap flow: tap → streamed answer, not just
  // a filled-in input box the user still has to send.
  useEffect(() => {
    if (app.chatPrefill && !sending) {
      const prompt = app.chatPrefill;
      app.setChatPrefill(null);
      // eslint-disable-next-line react-hooks/immutability -- send() is defined below; this effect runs after mount, so it is available
      send(prompt);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [app.chatPrefill]);

  const onScroll = (e: NativeSyntheticEvent<NativeScrollEvent>) => {
    const { contentOffset, contentSize, layoutMeasurement } = e.nativeEvent;
    const distanceFromBottom = contentSize.height - layoutMeasurement.height - contentOffset.y;
    pinnedToBottom.current = distanceFromBottom < 80;
  };

  // Content grows on every streamed token. Follow it only when pinned: a new
  // bubble (your question, or the answer starting) glides down; token-by-token
  // growth tracks instantly so the text scrolls up smoothly under your eyes.
  const onContentSizeChange = () => {
    if (!pinnedToBottom.current) return;
    const isNewTurn = app.chatMessages.length !== lastCount.current;
    lastCount.current = app.chatMessages.length;
    scrollRef.current?.scrollToEnd({ animated: isNewTurn });
  };

  const canSend = draft.trim().length > 0 && !sending;

  const applyEvent = (event: ChatEvent) => {
    app.setChatMessages((msgs) => {
      const last = msgs[msgs.length - 1];
      if (!last || last.role !== "assistant") return msgs;
      const updated = { ...last };
      const latestUserText = [...msgs].reverse().find((m) => m.role === "user")?.text ?? "";
      switch (event.kind) {
        case "tool_start":
          updated.chips = [
            ...updated.chips,
            { name: event.name, label: event.label, running: true },
          ];
          break;
        case "tool_end":
          updated.chips = updated.chips.map((c) =>
            c.name === event.name ? { ...c, running: false } : c,
          );
          if (event.result) {
            updated.widgets = [
              ...(updated.widgets ?? []),
              { name: event.name, result: event.result },
            ];
          }
          break;
        case "text":
          updated.text += event.delta;
          break;
        case "done":
          updated.sources = event.sources;
          updated.suggested = dynamicSuggestions({
            suggested: event.suggested,
            latestUserText,
            assistantText: updated.text,
            sources: event.sources,
            dashboard: app.dashboard,
          });
          updated.quality = event.quality;
          updated.isStreaming = false;
          break;
        case "error":
          updated.text = event.message;
          updated.isStreaming = false;
          break;
      }
      return [...msgs.slice(0, -1), updated];
    });
  };

  const send = async (textArg?: string) => {
    const text = (textArg ?? draft).trim();
    if (!text || sending) return;
    setDraft("");
    setSending(true);
    // A fresh question always anchors to the bottom, even if you'd scrolled up.
    pinnedToBottom.current = true;
    app.setChatMessages((msgs) => [
      ...msgs,
      newMessage({ role: "user", text, chips: [], sources: [], isStreaming: false }),
      newMessage({ role: "assistant", text: "", chips: [], sources: [], isStreaming: true }),
    ]);

    const conversationId = `${app.clientId}:${app.session}`;
    // Coalesce token deltas to one repaint per frame. GPT-4o streams tokens far
    // faster than 60fps, and each delta re-renders the whole ScrollView (no
    // virtualization) plus a scrollToEnd — applying every token individually
    // thrashes the UI thread. Buffer text and flush on rAF; flush eagerly before
    // any non-text event (tool widget, done) so ordering is preserved.
    let pendingText = "";
    let rafScheduled = false;
    const flushText = () => {
      rafScheduled = false;
      if (!pendingText) return;
      const delta = pendingText;
      pendingText = "";
      applyEvent({ kind: "text", delta });
    };
    for await (const event of app.api.chat(app.clientId, app.session, text, conversationId)) {
      if (event.kind === "text") {
        pendingText += event.delta;
        if (!rafScheduled) {
          rafScheduled = true;
          requestAnimationFrame(flushText);
        }
      } else {
        flushText();
        applyEvent(event);
      }
    }
    flushText();
    app.setChatMessages((msgs) => {
      const last = msgs[msgs.length - 1];
      if (!last || last.role !== "assistant") return msgs;
      return [
        ...msgs.slice(0, -1),
        { ...last, isStreaming: false, chips: last.chips.map((c) => ({ ...c, running: false })) },
      ];
    });
    setSending(false);
  };

  const sendFeedback = async (message: ChatMessage, rating: "positive" | "negative") => {
    const conversationId = `${app.clientId}:${app.session}`;
    app.setChatMessages((msgs) =>
      msgs.map((m) => (m.id === message.id ? { ...m, feedback: rating } : m)),
    );
    try {
      await app.api.sendFeedback({
        clientId: app.clientId,
        conversationId,
        messageId: message.id,
        rating,
        sources: message.sources,
        toolCalls: message.chips.map((chip) => chip.name),
        suggestions: message.suggested ?? [],
        answerPreview: message.text.slice(0, 500),
        quality: message.quality,
      });
    } catch {}
  };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.surfacePrimary }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        ref={scrollRef}
        contentContainerStyle={{
          padding: space[5],
          paddingTop: insets.top + space[2],
          gap: space[5],
        }}
        keyboardDismissMode="interactive"
        scrollEventThrottle={16}
        onScroll={onScroll}
        onContentSizeChange={onContentSizeChange}
      >
        <View style={styles.sessionHeader}>
          <View style={styles.sessionLine} />
          <Text style={styles.sessionText}>
            {app.session === "wednesday" ? "Wednesday, June 10" : "Monday, June 8"}
          </Text>
          <View style={styles.sessionLine} />
        </View>
        {app.chatMessages.map((message, i) => (
          <ChatMessageView
            key={message.id}
            message={message}
            showIdentity={app.chatMessages[i - 1]?.role !== "assistant"}
            onFeedback={sendFeedback}
            handoffDisabled={sending}
            onRevealed={handleRevealed}
          />
        ))}
        <SuggestionChips
          messages={app.chatMessages}
          sending={sending}
          revealedId={revealedId}
          onPick={send}
        />
      </ScrollView>

      <View style={styles.inputArea}>
        <DisclaimerFooter />
        <View style={styles.inputBar}>
          <TextInput
            style={styles.input}
            placeholder="Ask about your money…"
            placeholderTextColor={colors.inkTertiary}
            value={draft}
            onChangeText={setDraft}
            multiline
            onSubmitEditing={() => send()}
          />
          <Pressable onPress={() => send()} disabled={!canSend} style={{ paddingRight: 6 }}>
            <Ionicons
              name="arrow-up-circle"
              size={30}
              color={canSend ? colors.allworthAccent : colors.inkTertiary}
            />
          </Pressable>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

function SuggestionChips({
  messages,
  sending,
  revealedId,
  onPick,
}: {
  messages: ChatMessage[];
  sending: boolean;
  revealedId: string | null;
  onPick: (text: string) => void;
}) {
  const last = messages[messages.length - 1];
  if (sending || !last || last.role !== "assistant" || last.isStreaming) return null;
  // Hold the chips until the answer has fully typed in, not just when the stream ends.
  if (last.id !== revealedId) return null;
  const suggested = last.suggested ?? [];
  if (!suggested.length) return null;
  return (
    <View style={styles.suggestRow}>
      {suggested.map((s) => (
        <Pressable
          key={s}
          onPress={() => onPick(s)}
          style={({ pressed }) => [styles.suggestChip, pressed && { opacity: 0.7 }]}
        >
          <Text style={styles.suggestText}>{s}</Text>
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  sessionHeader: { flexDirection: "row", alignItems: "center", gap: space[3] },
  sessionLine: { flex: 1, height: StyleSheet.hairlineWidth, backgroundColor: colors.hairline },
  sessionText: {
    fontSize: 12,
    fontFamily: fonts.sansBold,
    color: colors.inkTertiary,
    letterSpacing: 0.4,
  },
  inputArea: { paddingHorizontal: space[5], paddingTop: 6, paddingBottom: space[3], gap: space[2] },
  // Restrained chips: hairline border, no fill, smaller body type — they assist
  // the answer rather than compete with the accent-filled handoff action.
  suggestRow: { flexDirection: "row", flexWrap: "wrap", gap: space[2] },
  suggestChip: {
    borderWidth: 1,
    borderColor: colors.hairline,
    borderRadius: radius.pill,
    paddingHorizontal: space[3],
    paddingVertical: 6,
  },
  suggestText: { ...text.bodySm, color: colors.inkSecondary },
  inputBar: { ...card, flexDirection: "row", alignItems: "center" },
  input: {
    flex: 1,
    fontSize: 17,
    fontFamily: fonts.sans,
    color: colors.inkPrimary,
    paddingHorizontal: 14,
    paddingVertical: 10,
    maxHeight: 100,
  },
});
