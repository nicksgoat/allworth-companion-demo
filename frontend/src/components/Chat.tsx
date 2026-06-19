import { Ionicons } from "@expo/vector-icons";
import React from "react";
import { Animated, StyleSheet, Text, View } from "react-native";
import { FadeScaleIn, usePulse } from "../anim";
import { colors, fonts } from "../theme";
import type { ChatMessage, ToolChip } from "../types";
import { AdvisorHandoffCard } from "./AdvisorHandoffCard";
import { ChatToolWidget } from "./ChatToolWidget";
import { AllworthMark } from "./Wordmark";

export function ToolChipRow({
  chips,
  sources,
  collapsed,
}: {
  chips: ToolChip[];
  sources: string[];
  collapsed: boolean;
}) {
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
          <ToolChipView key={chip.name} chip={chip} />
        ))}
      </View>
    );
  }
  return null;
}

// A softly pulsing dot reads as deliberate "thinking" — calmer and more premium
// than a spinner. Each chip also fades + scales in as the step begins.
function ThinkingDot() {
  const pulse = usePulse(0.3, 1, 620);
  return <Animated.View style={[styles.thinkingDot, { opacity: pulse }]} />;
}

function ToolChipView({ chip }: { chip: ToolChip }) {
  return (
    <FadeScaleIn>
      <View style={styles.chip}>
        {chip.running ? (
          <ThinkingDot />
        ) : (
          <Ionicons name="checkmark" size={11} color={colors.allworthAccent} />
        )}
        <Text style={styles.chipText}>{chip.label}</Text>
      </View>
    </FadeScaleIn>
  );
}

// Blinking caret while the answer streams in.
function TypingCursor() {
  const blink = usePulse(0.15, 1, 520);
  return <Animated.Text style={{ color: colors.inkTertiary, opacity: blink }}> ▍</Animated.Text>;
}

// Inline **bold** rendering that tolerates a half-streamed token: a trailing,
// not-yet-closed "**" renders its tail bold rather than flashing the asterisks.
function renderBold(text: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  let i = 0;
  let key = 0;
  while (i < text.length) {
    const open = text.indexOf("**", i);
    if (open === -1) {
      out.push(<Text key={key++}>{text.slice(i)}</Text>);
      break;
    }
    if (open > i) out.push(<Text key={key++}>{text.slice(i, open)}</Text>);
    const close = text.indexOf("**", open + 2);
    if (close === -1) {
      // Bold opened but not yet closed (still revealing) — render tail bold, no markers.
      out.push(
        <Text key={key++} style={{ fontFamily: fonts.sansBold }}>
          {text.slice(open + 2)}
        </Text>,
      );
      break;
    }
    out.push(
      <Text key={key++} style={{ fontFamily: fonts.sansBold }}>
        {text.slice(open + 2, close)}
      </Text>,
    );
    i = close + 2;
  }
  return out;
}

function MarkdownText({ text, streaming }: { text: string; streaming: boolean }) {
  return (
    <Text style={styles.assistantText}>
      {renderBold(text)}
      {streaming ? <TypingCursor /> : null}
    </Text>
  );
}

function AssistantIdentity() {
  return (
    <View style={styles.identityRow}>
      <View style={styles.avatar}>
        <AllworthMark size={14} color="#FFFFFF" />
      </View>
      <Text style={styles.identityName}>Allworth Assistant</Text>
    </View>
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
      <AssistantIdentity />
      <ToolChipRow
        chips={message.chips}
        sources={message.sources}
        collapsed={!message.isStreaming}
      />
      {message.widgets?.map((w, i) => (
        <ChatToolWidget key={`${w.name}-${i}`} widget={w} />
      ))}
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
  sourcesText: { fontSize: 13, fontFamily: fonts.sans, color: colors.inkTertiary, flex: 1 },
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
  chipText: { fontSize: 13, fontFamily: fonts.sans, color: colors.inkSecondary },
  thinkingDot: { width: 7, height: 7, borderRadius: 3.5, backgroundColor: colors.allworthAccent },
  userRow: { flexDirection: "row", justifyContent: "flex-end", paddingLeft: 48 },
  userBubble: {
    backgroundColor: colors.inkFaint,
    borderRadius: 16,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  userText: { fontSize: 17, fontFamily: fonts.sans, color: colors.inkPrimary },
  assistantText: { fontSize: 17, fontFamily: fonts.sans, color: colors.inkPrimary, lineHeight: 24 },
  identityRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  avatar: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: colors.allworthNavy,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarText: { fontSize: 12, fontFamily: fonts.sansBold, color: "#FFFFFF" },
  identityName: { fontSize: 13, fontFamily: fonts.sansBold, color: colors.inkSecondary },
});
