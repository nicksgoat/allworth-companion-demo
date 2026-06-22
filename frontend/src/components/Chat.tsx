import { Ionicons } from "@expo/vector-icons";
import React from "react";
import { Animated, Platform, Pressable, StyleSheet, Text, View } from "react-native";
import { FadeScaleIn, usePulse } from "../anim";
import { colors, fonts } from "../theme";
import type { ChatMessage, ToolChip } from "../types";
import { AdvisorHandoffCard } from "./AdvisorHandoffCard";
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
    <Text style={[styles.assistantText, webTextWrap]}>
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

export function ChatMessageView({
  message,
  onFeedback,
  onAdvisorHandoff,
  handoffDisabled,
}: {
  message: ChatMessage;
  onFeedback?: (message: ChatMessage, rating: "positive" | "negative") => void;
  onAdvisorHandoff?: (message: ChatMessage, action: "message" | "schedule") => void;
  handoffDisabled?: boolean;
}) {
  if (message.role === "user") {
    return (
      <View style={styles.userRow}>
        <View style={styles.userBubble}>
          <Text style={[styles.userText, webTextWrap]}>{message.text}</Text>
        </View>
      </View>
    );
  }
  return (
    <View style={styles.assistantBlock}>
      <AssistantIdentity />
      <ToolChipRow
        chips={message.chips}
        sources={message.sources}
        collapsed={!message.isStreaming}
      />
      {message.text ? <MarkdownText text={message.text} streaming={message.isStreaming} /> : null}
      {!message.isStreaming && message.sources.length > 0 ? (
        <View style={{ paddingTop: 4 }}>
          <AdvisorHandoffCard
            disabled={handoffDisabled}
            onMessage={() => onAdvisorHandoff?.(message, "message")}
            onSchedule={() => onAdvisorHandoff?.(message, "schedule")}
          />
        </View>
      ) : null}
      {!message.isStreaming && message.text ? (
        <View style={styles.feedbackRow}>
          <Text style={styles.feedbackLabel}>Was this helpful?</Text>
          <Pressable
            onPress={() => onFeedback?.(message, "positive")}
            style={[
              styles.feedbackButton,
              message.feedback === "positive" && styles.feedbackButtonSelected,
            ]}
          >
            <Ionicons
              name="thumbs-up-outline"
              size={14}
              color={message.feedback === "positive" ? colors.allworthAccent : colors.inkTertiary}
            />
          </Pressable>
          <Pressable
            onPress={() => onFeedback?.(message, "negative")}
            style={[
              styles.feedbackButton,
              message.feedback === "negative" && styles.feedbackButtonSelected,
            ]}
          >
            <Ionicons
              name="thumbs-down-outline"
              size={14}
              color={message.feedback === "negative" ? colors.allworthAccent : colors.inkTertiary}
            />
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}

const webTextWrap =
  Platform.OS === "web"
    ? ({
        whiteSpace: "pre-wrap",
        overflowWrap: "break-word",
        wordBreak: "break-word",
      } as any)
    : null;

const styles = StyleSheet.create({
  sourcesRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  sourcesText: {
    fontSize: 13,
    fontFamily: fonts.sans,
    color: colors.inkTertiary,
    flex: 1,
    flexShrink: 1,
    minWidth: 0,
  },
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
  userRow: { flexDirection: "row", justifyContent: "flex-end", paddingLeft: 48, maxWidth: "100%" },
  userBubble: {
    backgroundColor: colors.inkFaint,
    borderRadius: 16,
    paddingHorizontal: 14,
    paddingVertical: 10,
    maxWidth: "100%",
    flexShrink: 1,
  },
  userText: {
    fontSize: 17,
    fontFamily: fonts.sans,
    color: colors.inkPrimary,
    flexShrink: 1,
    minWidth: 0,
  },
  assistantBlock: {
    gap: 10,
    alignSelf: "stretch",
    maxWidth: "100%",
    flexShrink: 1,
    minWidth: 0,
  },
  assistantText: {
    fontSize: 17,
    fontFamily: fonts.sans,
    color: colors.inkPrimary,
    lineHeight: 24,
    alignSelf: "stretch",
    maxWidth: "100%",
    flexShrink: 1,
    minWidth: 0,
  },
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
  feedbackRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  feedbackLabel: { fontSize: 12, fontFamily: fonts.sans, color: colors.inkTertiary },
  feedbackButton: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.inkFaint,
  },
  feedbackButtonSelected: { borderWidth: 1, borderColor: colors.allworthAccent },
});
