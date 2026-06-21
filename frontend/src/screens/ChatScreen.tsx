import { Ionicons } from "@expo/vector-icons";
import React, { useEffect, useRef, useState } from "react";
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
import { card, colors, fonts } from "../theme";
import type { ChatEvent, ChatMessage } from "../types";

let nextId = 1;
const newMessage = (m: Omit<ChatMessage, "id">): ChatMessage => ({ ...m, id: String(nextId++) });

export function ChatScreen() {
  const app = useApp();
  const insets = useSafeAreaInsets();
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
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
          updated.suggested = event.suggested;
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

    for await (const event of app.api.chat(app.clientId, app.session, text)) {
      applyEvent(event);
    }
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

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.surfacePrimary }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        ref={scrollRef}
        contentContainerStyle={{ padding: 20, paddingTop: insets.top + 8, gap: 24 }}
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
          <ChatMessageView key={message.id} message={message} />
        ))}
        <SuggestionChips messages={app.chatMessages} sending={sending} onPick={send} />
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
  onPick,
}: {
  messages: ChatMessage[];
  sending: boolean;
  onPick: (text: string) => void;
}) {
  const last = messages[messages.length - 1];
  if (sending || !last || last.role !== "assistant" || last.isStreaming) return null;
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
  sessionHeader: { flexDirection: "row", alignItems: "center", gap: 12, marginBottom: -8 },
  sessionLine: { flex: 1, height: StyleSheet.hairlineWidth, backgroundColor: colors.hairline },
  sessionText: {
    fontSize: 12,
    fontFamily: fonts.sansBold,
    color: colors.inkTertiary,
    letterSpacing: 0.4,
  },
  inputArea: { paddingHorizontal: 20, paddingTop: 6, paddingBottom: 10, gap: 8 },
  suggestRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: -8 },
  suggestChip: {
    borderWidth: 1,
    borderColor: colors.allworthAccent,
    borderRadius: 999,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  suggestText: { fontSize: 14, fontFamily: fonts.sansBold, color: colors.allworthAccent },
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
