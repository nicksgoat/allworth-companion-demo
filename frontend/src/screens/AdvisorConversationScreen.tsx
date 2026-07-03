import { Ionicons } from "@expo/vector-icons";
import React, { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useApp } from "../state";
import { colors, fonts, radius, space, text } from "../theme";
import type { ConversationMessage } from "../types";

// The advisor's full-screen view of a client's assistant thread — a real chat
// surface, not a transcript list. From the advisor's seat: their own posts sit
// right in navy, the client's sit left in white cards, and assistant turns are
// muted context between the humans. Demo-grade 4s polling.
export function AdvisorConversationView({
  clientId,
  clientName,
}: {
  clientId: string;
  clientName: string;
}) {
  const app = useApp();
  const insets = useSafeAreaInsets();
  const [messages, setMessages] = useState<ConversationMessage[] | null>(null);
  const [draft, setDraft] = useState("");
  const [posting, setPosting] = useState(false);
  const scrollRef = useRef<ScrollView>(null);
  const lastCount = useRef(0);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const res = await app.api.conversation(clientId, app.session);
        if (!cancelled) setMessages(res.messages);
      } catch {}
    };
    tick();
    const interval = setInterval(tick, 4000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId, app.session]);

  // Follow the thread as it grows (new poll results or own sends).
  useEffect(() => {
    const count = messages?.length ?? 0;
    if (count !== lastCount.current) {
      lastCount.current = count;
      requestAnimationFrame(() => scrollRef.current?.scrollToEnd({ animated: true }));
    }
  }, [messages]);

  const send = async () => {
    const body = draft.trim();
    if (!body || posting) return;
    setPosting(true);
    try {
      await app.api.interject(clientId, app.session, body);
      setDraft("");
      const res = await app.api.conversation(clientId, app.session);
      setMessages(res.messages);
    } catch {}
    setPosting(false);
  };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.surfacePrimary }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      keyboardVerticalOffset={100}
    >
      {messages === null ? (
        <ActivityIndicator style={{ paddingTop: 100 }} />
      ) : messages.length === 0 ? (
        <View style={styles.emptyWrap}>
          <Ionicons name="chatbubbles-outline" size={28} color={colors.inkTertiary} />
          <Text style={styles.emptyText}>
            No thread yet — {clientName}
            {"'"}s next assistant chat will appear here live.
          </Text>
        </View>
      ) : (
        <ScrollView
          ref={scrollRef}
          style={{ flex: 1 }}
          contentContainerStyle={{ padding: space[5], gap: space[3], paddingBottom: space[2] }}
        >
          {messages.map((m) => (
            <TranscriptBubble key={`${m.seq}-${m.id ?? "t"}`} message={m} clientName={clientName} />
          ))}
        </ScrollView>
      )}

      <View style={[styles.composerBar, { paddingBottom: Math.max(insets.bottom, space[3]) }]}>
        <View style={styles.composerRow}>
          <TextInput
            style={styles.input}
            placeholder={`Message ${clientName} in this thread…`}
            placeholderTextColor={colors.inkTertiary}
            value={draft}
            onChangeText={setDraft}
            multiline
            editable={!posting}
          />
          <Pressable
            onPress={send}
            disabled={!draft.trim() || posting}
            style={[styles.sendOrb, (!draft.trim() || posting) && { opacity: 0.35 }]}
          >
            {posting ? (
              <ActivityIndicator size="small" color="#FFFFFF" />
            ) : (
              <Ionicons name="arrow-up" size={18} color="#FFFFFF" />
            )}
          </Pressable>
        </View>
        <Text style={styles.hint}>
          Posts as you into {clientName}
          {"'"}s thread — the assistant treats it as advisor context.
        </Text>
      </View>
    </KeyboardAvoidingView>
  );
}

function TranscriptBubble({
  message,
  clientName,
}: {
  message: ConversationMessage;
  clientName: string;
}) {
  if (message.role === "advisor") {
    // You. Right-aligned, navy — the advisor owns these words.
    return (
      <View style={styles.advisorWrap}>
        <View style={styles.advisorBubble}>
          <Text style={styles.advisorText}>{message.text}</Text>
        </View>
        <Text style={styles.metaRight}>{(message.advisorName ?? "You").split(" ")[0]} · you</Text>
      </View>
    );
  }

  if (message.role === "user") {
    // The client. Left-aligned white card with their initials.
    return (
      <View style={styles.clientWrap}>
        <View style={styles.clientAvatar}>
          <Text style={styles.clientAvatarText}>{clientName[0]?.toUpperCase() ?? "C"}</Text>
        </View>
        <View style={{ flexShrink: 1, gap: 3 }}>
          <View style={styles.clientBubble}>
            <Text style={styles.clientText}>{message.text}</Text>
          </View>
          <Text style={styles.metaLeft}>{clientName}</Text>
        </View>
      </View>
    );
  }

  // The assistant — context between the humans, deliberately quiet.
  return (
    <View style={styles.assistantWrap}>
      <View style={styles.assistantLabelRow}>
        <Ionicons name="sparkles" size={11} color={colors.inkTertiary} />
        <Text style={styles.assistantLabel}>Assistant</Text>
      </View>
      <Text style={styles.assistantText} numberOfLines={6}>
        {message.text}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  emptyWrap: { flex: 1, alignItems: "center", justifyContent: "center", gap: space[3], padding: 40 },
  emptyText: { ...text.body, color: colors.inkTertiary, textAlign: "center", lineHeight: 21 },

  advisorWrap: { alignItems: "flex-end", gap: 3 },
  advisorBubble: {
    maxWidth: "82%",
    backgroundColor: colors.allworthNavy,
    borderRadius: radius.card,
    borderBottomRightRadius: 6,
    paddingHorizontal: space[4],
    paddingVertical: space[3],
  },
  advisorText: { fontSize: 15, fontFamily: fonts.sans, color: "#FFFFFF", lineHeight: 21 },
  metaRight: { fontSize: 11, fontFamily: fonts.sans, color: colors.inkTertiary },

  clientWrap: { flexDirection: "row", alignItems: "flex-end", gap: space[2], maxWidth: "88%" },
  clientAvatar: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: colors.inkFaint,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 18,
  },
  clientAvatarText: { fontSize: 12, fontFamily: fonts.sansBold, color: colors.inkSecondary },
  clientBubble: {
    backgroundColor: colors.surfaceCard,
    borderRadius: radius.card,
    borderBottomLeftRadius: 6,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.hairline,
    paddingHorizontal: space[4],
    paddingVertical: space[3],
  },
  clientText: { fontSize: 15, fontFamily: fonts.sans, color: colors.inkPrimary, lineHeight: 21 },
  metaLeft: { fontSize: 11, fontFamily: fonts.sans, color: colors.inkTertiary, paddingLeft: 4 },

  assistantWrap: {
    gap: 3,
    paddingLeft: space[3],
    borderLeftWidth: 2,
    borderLeftColor: colors.inkFaint,
    marginVertical: 2,
  },
  assistantLabelRow: { flexDirection: "row", alignItems: "center", gap: 4 },
  assistantLabel: {
    fontSize: 10,
    fontFamily: fonts.sansBold,
    color: colors.inkTertiary,
    letterSpacing: 0.5,
    textTransform: "uppercase",
  },
  assistantText: { ...text.bodySm, color: colors.inkSecondary, lineHeight: 19 },

  composerBar: {
    paddingHorizontal: space[4],
    paddingTop: space[2],
    gap: space[1],
    backgroundColor: colors.surfacePrimary,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.hairline,
  },
  composerRow: { flexDirection: "row", alignItems: "flex-end", gap: space[2] },
  input: {
    flex: 1,
    fontSize: 15,
    fontFamily: fonts.sans,
    color: colors.inkPrimary,
    backgroundColor: colors.surfaceCard,
    borderWidth: 1,
    borderColor: colors.hairline,
    borderRadius: 22,
    paddingHorizontal: space[4],
    paddingVertical: 10,
    maxHeight: 110,
    ...(Platform.OS === "web" ? ({ outlineStyle: "none" } as any) : null),
  },
  sendOrb: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: colors.allworthNavy,
    alignItems: "center",
    justifyContent: "center",
  },
  hint: { fontSize: 11, fontFamily: fonts.sans, color: colors.inkTertiary },
});
