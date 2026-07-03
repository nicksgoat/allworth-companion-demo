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
import { AllworthMark } from "../components/Wordmark";
import { useApp } from "../state";
import { colors, fonts, radius, shadowSoft, space, text } from "../theme";
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
  const inputRef = useRef<TextInput>(null);
  // A floating "scroll to bottom" pill (ChatGPT-style) shows once you've scrolled
  // meaningfully up from the latest message.
  const [showScrollDown, setShowScrollDown] = useState(false);
  // "Stick to bottom": follow a streaming answer only while you're already at
  // the bottom. The moment you scroll up to read, we stop following so the
  // text never yanks you back down mid-read.
  const pinnedToBottom = useRef(true);
  const lastCount = useRef(0);
  // Bumped on "new chat" so an in-flight stream from the old thread can't
  // write into the fresh one (applyEvent targets the last assistant message,
  // which after a reset would be the new greeting).
  const threadEpoch = useRef(0);

  const buildGreeting = async (): Promise<ChatMessage> => {
    const clientFirstName = app.dashboard?.client?.name?.split(",")[0]?.split(" ")[0] ?? "there";
    let greeting = `Hi ${clientFirstName} — I can help you understand your accounts, spending, or plan. What's on your mind?`;
    let suggested: string[] = [];
    try {
      const res = await app.api.proactive(app.clientId, app.session);
      greeting = res.message;
      suggested = res.suggested ?? [];
    } catch {}
    return newMessage({
      role: "assistant",
      text: greeting,
      chips: [],
      sources: [],
      isStreaming: false,
      suggested,
    });
  };

  const loadProactive = async () => {
    if (app.chatMessages.length > 0) return;
    const greeting = await buildGreeting();
    app.setChatMessages((msgs) => (msgs.length > 0 ? msgs : [greeting]));
  };

  // The header's compose button: wipe the thread and drop back to a fresh
  // proactive greeting — the ChatGPT "new chat" gesture. Bumping the epoch
  // orphans any answer still streaming into the old thread.
  const startNewChat = async () => {
    threadEpoch.current += 1;
    setSending(false);
    setDraft("");
    setRevealedId(null);
    app.setChatMessages([]);
    const greeting = await buildGreeting();
    app.setChatMessages([greeting]);
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
    setShowScrollDown(distanceFromBottom > 240);
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

  const hasText = draft.trim().length > 0;
  const canSend = hasText && !sending;

  const scrollToBottom = () => {
    pinnedToBottom.current = true;
    setShowScrollDown(false);
    scrollRef.current?.scrollToEnd({ animated: true });
  };

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
    const epoch = threadEpoch.current;
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
      if (threadEpoch.current !== epoch) {
        pendingText = "";
        return;
      }
      const delta = pendingText;
      pendingText = "";
      applyEvent({ kind: "text", delta });
    };
    for await (const event of app.api.chat(app.clientId, app.session, text, conversationId)) {
      // New chat started mid-stream: abandon this answer (breaking closes the
      // stream) and leave the fresh thread untouched.
      if (threadEpoch.current !== epoch) break;
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
    if (threadEpoch.current !== epoch) return;
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

  // Who you're talking to: the household's assigned advisor's assistant
  // ("Nicole's Assistant"), falling back to the brand name if no advisor is set.
  const advisorFullName = app.dashboard?.advisor?.name;
  const assistantTitle = advisorFullName
    ? `${advisorFullName.split(" ")[0]}'s Assistant`
    : "Allworth Assistant";

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.surfacePrimary }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ChatHeader topInset={insets.top} title={assistantTitle} onNewChat={startNewChat} />
      <View style={{ flex: 1 }}>
        <ScrollView
          ref={scrollRef}
          contentContainerStyle={{ padding: space[5], paddingTop: space[3], gap: space[5] }}
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
          {app.chatMessages.map((message) => (
            <ChatMessageView
              key={message.id}
              message={message}
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
        {showScrollDown ? (
          <Pressable onPress={scrollToBottom} style={styles.scrollDownBtn} hitSlop={6}>
            <Ionicons name="arrow-down" size={20} color={colors.inkSecondary} />
          </Pressable>
        ) : null}
      </View>

      <View style={styles.inputArea}>
        <DisclaimerFooter />
        <View style={styles.inputBar}>
          <TextInput
            ref={inputRef}
            style={styles.input}
            placeholder="Ask Allworth…"
            placeholderTextColor={colors.inkTertiary}
            value={draft}
            onChangeText={setDraft}
            multiline
            onSubmitEditing={() => send()}
          />
          {/* Send appears only once there's something to send — no attachments,
              no voice affordance, just the one action that matters. */}
          {hasText ? (
            <Pressable
              onPress={() => send()}
              disabled={!canSend}
              style={[styles.orb, !canSend && { opacity: 0.5 }]}
            >
              <Ionicons name="arrow-up" size={20} color="#FFFFFF" />
            </Pressable>
          ) : null}
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

// ChatGPT-style top bar: brand mark + the advisor's-assistant identity on the
// left ("Nicole's Assistant" — who you're talking to), a compose button on the
// right that starts a fresh conversation.
function ChatHeader({
  topInset,
  title,
  onNewChat,
}: {
  topInset: number;
  title: string;
  onNewChat: () => void;
}) {
  return (
    <View style={[styles.header, { paddingTop: topInset + 6 }]}>
      <View style={styles.headerBrand}>
        <View style={styles.headerMark}>
          <AllworthMark size={18} color={colors.allworthNavy} />
        </View>
        <Text style={styles.headerTitle} numberOfLines={1}>
          {title}
        </Text>
      </View>
      <Pressable
        onPress={onNewChat}
        hitSlop={8}
        style={({ pressed }) => [styles.headerBtn, pressed && { opacity: 0.6 }]}
      >
        <Ionicons name="create-outline" size={22} color={colors.inkPrimary} />
      </Pressable>
    </View>
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
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: space[4],
    paddingBottom: space[2],
    backgroundColor: colors.surfacePrimary,
  },
  headerBrand: { flexDirection: "row", alignItems: "center", gap: space[2] },
  headerMark: {
    width: 32,
    height: 32,
    borderRadius: 10,
    backgroundColor: colors.surfaceCard,
    alignItems: "center",
    justifyContent: "center",
    ...shadowSoft,
  },
  headerTitle: { fontSize: 17, fontFamily: fonts.sansBold, color: colors.inkPrimary },
  headerBtn: {
    width: 36,
    height: 36,
    borderRadius: 12,
    backgroundColor: colors.surfaceCard,
    alignItems: "center",
    justifyContent: "center",
    ...shadowSoft,
  },
  sessionHeader: { flexDirection: "row", alignItems: "center", gap: space[3] },
  sessionLine: { flex: 1, height: StyleSheet.hairlineWidth, backgroundColor: colors.hairline },
  sessionText: {
    fontSize: 12,
    fontFamily: fonts.sansBold,
    color: colors.inkTertiary,
    letterSpacing: 0.4,
  },
  // Floating "jump to latest" pill, centered just above the composer.
  scrollDownBtn: {
    position: "absolute",
    alignSelf: "center",
    bottom: 10,
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: colors.surfaceCard,
    borderWidth: 1,
    borderColor: colors.hairline,
    alignItems: "center",
    justifyContent: "center",
    ...shadowSoft,
  },
  inputArea: { paddingHorizontal: space[4], paddingTop: 6, paddingBottom: space[3], gap: space[2] },
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
  // ChatGPT composer: a rounded pill that grows upward as the draft wraps, with
  // a single send orb on the right that appears only once there's text.
  inputBar: {
    flexDirection: "row",
    alignItems: "flex-end",
    gap: 6,
    backgroundColor: colors.surfaceCard,
    borderRadius: 26,
    borderWidth: 1,
    borderColor: colors.hairline,
    paddingVertical: 5,
    paddingHorizontal: 8,
    ...shadowSoft,
  },
  input: {
    flex: 1,
    fontSize: 17,
    fontFamily: fonts.sans,
    color: colors.inkPrimary,
    paddingLeft: 10,
    paddingRight: 4,
    paddingTop: Platform.OS === "ios" ? 8 : 4,
    paddingBottom: Platform.OS === "ios" ? 8 : 4,
    maxHeight: 120,
  },
  orb: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: colors.allworthNavy,
    alignItems: "center",
    justifyContent: "center",
  },
});
