import { Ionicons } from "@expo/vector-icons";
import React from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { colors } from "../theme";
import type { ChatMessage, ToolChip } from "../types";
import { AdvisorHandoffCard } from "./AdvisorHandoffCard";

export function ToolChipRow({ chips, sources, collapsed }: { chips: ToolChip[]; sources: string[]; collapsed: boolean }) {
  if (collapsed && sources.length > 0) {
    return (
      <View style={styles.sourcesRow}>
        <Ionicons name="search-outline" size={12} color={colors.inkTertiary} />
        <Text style={styles.sourcesText}>Sources: {sources.join(" · ")}</Text>
      </View>
    );
  }
  if (!collapsed && chips.length > 0) {
    return (
      <View style={styles.chipFlow}>
        {chips.map((chip) => (
          <View key={chip.name} style={styles.chip}>
            {chip.running ? (
              <ActivityIndicator size="small" color={colors.inkSecondary} style={{ transform: [{ scale: 0.7 }] }} />
            ) : (
              <Ionicons name="checkmark" size={11} color={colors.allworthAccent} />
            )}
            <Text style={styles.chipText}>{chip.label}</Text>
          </View>
        ))}
      </View>
    );
  }
  return null;
}

// Inline **bold** rendering — matches the Swift inline-markdown treatment.
function MarkdownText({ text, streaming }: { text: string; streaming: boolean }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <Text style={styles.assistantText}>
      {parts.map((part, i) =>
        part.startsWith("**") && part.endsWith("**") ? (
          <Text key={i} style={{ fontWeight: "600" }}>
            {part.slice(2, -2)}
          </Text>
        ) : (
          <Text key={i}>{part}</Text>
        )
      )}
      {streaming ? <Text style={{ color: colors.inkTertiary }}> ▍</Text> : null}
    </Text>
  );
}

export function ChatMessageView({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <View style={styles.userRow}>
        <View style={styles.userBubble}>
          <Text style={styles.userText}>{message.text}</Text>
        </View>
      </View>
    );
  }
  return (
    <View style={{ gap: 10 }}>
      <ToolChipRow chips={message.chips} sources={message.sources} collapsed={!message.isStreaming} />
      {message.text ? <MarkdownText text={message.text} streaming={message.isStreaming} /> : null}
      {!message.isStreaming && message.sources.length > 0 ? (
        <View style={{ paddingTop: 4 }}>
          <AdvisorHandoffCard />
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  sourcesRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  sourcesText: { fontSize: 13, color: colors.inkTertiary, flex: 1 },
  chipFlow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 999,
    backgroundColor: colors.inkFaint,
  },
  chipText: { fontSize: 13, color: colors.inkSecondary },
  userRow: { flexDirection: "row", justifyContent: "flex-end", paddingLeft: 48 },
  userBubble: {
    backgroundColor: colors.inkFaint,
    borderRadius: 16,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  userText: { fontSize: 17, color: colors.inkPrimary },
  assistantText: { fontSize: 17, color: colors.inkPrimary, lineHeight: 24 },
});
