import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import React, { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useApp } from "../state";
import { card, colors, fonts } from "../theme";

// The most important recurring component: every analytical answer and nudge ends here.
export function AdvisorHandoffCard({
  advisorName,
  advisorInitials,
  advisorTitle,
  onMessage,
  onSchedule,
  disabled,
}: {
  advisorName?: string;
  advisorInitials?: string;
  advisorTitle?: string;
  onMessage?: () => void;
  onSchedule?: () => void;
  disabled?: boolean;
}) {
  const { dashboard } = useApp();
  const name = advisorName ?? dashboard?.advisor?.name ?? "Your Advisor";
  const initials = advisorInitials ?? dashboard?.advisor?.avatarInitials ?? "??";
  const title = advisorTitle ?? dashboard?.advisor?.title ?? "Financial Advisor";
  const [requestedAction, setRequestedAction] = useState<"message" | "schedule" | null>(null);
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
  buttons: { flexDirection: "row", gap: 10 },
  button: { flex: 1, paddingVertical: 10, borderRadius: 10, alignItems: "center" },
  buttonText: { fontSize: 15, fontFamily: fonts.sansBold },
  sentRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  sentText: { fontSize: 15, fontFamily: fonts.sans, color: colors.allworthAccent },
});
