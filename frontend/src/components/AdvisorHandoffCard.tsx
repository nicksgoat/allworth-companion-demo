import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import React, { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useApp } from "../state";
import { card, colors, fonts, radius, space, text } from "../theme";

// The most important recurring component: every analytical answer and nudge ends here.
// `compact` renders a single inline "Bring this to {advisor} →" row that reveals the
// Message/Schedule actions on tap, for dense surfaces like the chat stream. Default
// stays the full bordered card used by Invest / Position / Nudge screens.
export function AdvisorHandoffCard({
  advisorName,
  advisorInitials,
  advisorTitle,
  onMessage,
  onSchedule,
  disabled,
  compact,
}: {
  advisorName?: string;
  advisorInitials?: string;
  advisorTitle?: string;
  onMessage?: () => void;
  onSchedule?: () => void;
  disabled?: boolean;
  compact?: boolean;
}) {
  const { dashboard } = useApp();
  const name = advisorName ?? dashboard?.advisor?.name ?? "Your Advisor";
  const initials = advisorInitials ?? dashboard?.advisor?.avatarInitials ?? "??";
  const title = advisorTitle ?? dashboard?.advisor?.title ?? "Financial Advisor";
  const [requestedAction, setRequestedAction] = useState<"message" | "schedule" | null>(null);
  const [expanded, setExpanded] = useState(false);
  const firstName = name.split(" ")[0];

  const requestDraft = (action: "message" | "schedule") => {
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    setRequestedAction(action);
  };

  const handleMessage = () => {
    requestDraft("message");
    onMessage?.();
  };

  const handleSchedule = () => {
    requestDraft("schedule");
    onSchedule?.();
  };

  const requestedText =
    requestedAction === "schedule"
      ? `Preparing an agenda for ${firstName} in chat`
      : `Drafting a note for ${firstName} in chat`;

  if (compact) {
    if (requestedAction) {
      return (
        <View style={styles.compactSentRow}>
          <Ionicons name="checkmark-circle" size={16} color={colors.allworthAccent} />
          <Text style={styles.sentText}>{requestedText}</Text>
        </View>
      );
    }
    return (
      <View style={styles.compactWrap}>
        <Pressable
          onPress={() => setExpanded((v) => !v)}
          disabled={disabled}
          style={({ pressed }) => [styles.compactTrigger, pressed && { opacity: 0.6 }]}
        >
          <Ionicons name="chatbubble-ellipses-outline" size={15} color={colors.allworthAccent} />
          <Text style={styles.compactTriggerText}>Bring this to {firstName}</Text>
          <Ionicons
            name={expanded ? "chevron-up" : "chevron-forward"}
            size={14}
            color={colors.inkTertiary}
          />
        </Pressable>
        {expanded ? (
          <View style={styles.buttons}>
            <HandoffButton label="Message" filled onPress={handleMessage} disabled={disabled} />
            <HandoffButton label="Schedule" onPress={handleSchedule} disabled={disabled} />
          </View>
        ) : null}
      </View>
    );
  }

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>{initials}</Text>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>Bring this to {firstName}</Text>
          <Text style={styles.subtitle}>{title}</Text>
        </View>
      </View>
      {requestedAction ? (
        <View style={styles.sentRow}>
          <Ionicons name="checkmark-circle" size={17} color={colors.allworthAccent} />
          <Text style={styles.sentText}>{requestedText}</Text>
        </View>
      ) : (
        <View style={styles.buttons}>
          <HandoffButton label="Message" filled onPress={handleMessage} disabled={disabled} />
          <HandoffButton label="Schedule" onPress={handleSchedule} disabled={disabled} />
        </View>
      )}
    </View>
  );
}

function HandoffButton({
  label,
  filled,
  onPress,
  disabled,
}: {
  label: string;
  filled?: boolean;
  onPress: () => void;
  disabled?: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: filled ? colors.allworthAccent : "rgba(62,113,183,0.12)" },
        disabled && { opacity: 0.45 },
        pressed && { opacity: 0.85 },
      ]}
    >
      <Text style={[styles.buttonText, { color: filled ? "#fff" : colors.allworthAccent }]}>
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  // Compact inline variant (chat stream): a light single-row affordance.
  compactWrap: { gap: space[2] },
  compactTrigger: {
    flexDirection: "row",
    alignItems: "center",
    gap: space[2],
    alignSelf: "flex-start",
  },
  compactTriggerText: {
    ...text.bodySm,
    fontFamily: fonts.sansBold,
    color: colors.allworthAccent,
  },
  compactSentRow: { flexDirection: "row", alignItems: "center", gap: space[2] },

  card: { ...card, padding: 16, gap: 14 },
  header: { flexDirection: "row", alignItems: "center", gap: 12 },
  avatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.allworthNavy,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarText: { color: "#fff", fontSize: 16, fontFamily: fonts.sansBold },
  title: { fontSize: 17, fontFamily: fonts.sansBold, color: colors.inkPrimary },
  subtitle: { fontSize: 13, fontFamily: fonts.sans, color: colors.inkSecondary, marginTop: 2 },
  buttons: { flexDirection: "row", gap: space[3] },
  button: { flex: 1, paddingVertical: space[3], borderRadius: radius.chip, alignItems: "center" },
  buttonText: { fontSize: 15, fontFamily: fonts.sansBold },
  sentRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  sentText: { ...text.bodySm, color: colors.allworthAccent },
});
