import { Ionicons } from "@expo/vector-icons";
import React, { useEffect, useRef, useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { ChatMessageView } from "../components/Chat";
import { DisclaimerFooter } from "../components/Rows";
import { useApp } from "../state";
import { card, colors } from "../theme";
import type { ChatEvent, ChatMessage } from "../types";

let nextId = 1;
const newMessage = (m: Omit<ChatMessage, "id">): ChatMessage => ({ ...m, id: String(nextId++) });

export function ChatScreen() {
  const app = useApp();
  const insets = useSafeAreaInsets();
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    loadProactive();
  }, [app.session]);

  useEffect(() => {
    if (app.chatPrefill) {
      setDraft(app.chatPrefill);
      app.setChatPrefill(null);
    }
  }, [app.chatPrefill]);

  useEffect(() => {
    scrollRef.current?.scrollToEnd({ animated: true });
  }, [app.chatMessages]);

  const loadProactive = async () => {
    if (app.chatMessages.length > 0) return;
    let greeting = "Hi Maya — I can help you understand your accounts, spending, or plan. What's on your mind?";
    try {
      greeting = (await app.api.proactive(app.clientId, app.session)).message;
    } catch {}
    app.setChatMessages((msgs) =>
      msgs.length > 0
        ? msgs
        : [newMessage({ role: "assistant", text: greeting, chips: [], sources: [], isStreaming: false })]
    );
  };

  const canSend = draft.trim().length > 0 && !sending;

  const applyEvent = (event: ChatEvent) => {
    app.setChatMessages((msgs) => {
      const last = msgs[msgs.length - 1];
      if (!last || last.role !== "assistant") return msgs;
      const updated = { ...last };
      switch (event.kind) {
        case "tool_start":
          updated.chips = [...updated.chips, { name: event.name, label: event.label, running: true }];
          break;
        case "tool_end":
          updated.chips = updated.chips.map((c) => (c.name === event.name ? { ...c, running: false } : c));
          break;
        case "text":
          updated.text += event.delta;
          break;
        case "done":
          updated.sources = event.sources;
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

  const send = async () => {
    if (!canSend) return;
    const text = draft.trim();
    setDraft("");
    setSending(true);
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
      >
        {app.chatMessages.map((message) => (
          <ChatMessageView key={message.id} message={message} />
        ))}
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
            onSubmitEditing={send}
          />
          <Pressable onPress={send} disabled={!canSend} style={{ paddingRight: 6 }}>
            <Ionicons name="arrow-up-circle" size={30} color={canSend ? colors.allworthAccent : colors.inkTertiary} />
          </Pressable>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  inputArea: { paddingHorizontal: 20, paddingTop: 6, paddingBottom: 10, gap: 8 },
  inputBar: { ...card, flexDirection: "row", alignItems: "center" },
  input: {
    flex: 1,
    fontSize: 17,
    color: colors.inkPrimary,
    paddingHorizontal: 14,
    paddingVertical: 10,
    maxHeight: 100,
  },
});
