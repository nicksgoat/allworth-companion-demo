import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import React, { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { card, colors } from "../theme";

// The most important recurring component: every analytical answer and nudge ends here.
export function AdvisorHandoffCard({
  advisorName = "Dana Whitfield",
  advisorInitials = "DW",
  advisorTitle = "Senior Financial Advisor, CFP®",
}: {
  advisorName?: string;
  advisorInitials?: string;
  advisorTitle?: string;
}) {
  const [sent, setSent] = useState(false);
  const firstName = advisorName.split(" ")[0];

  const send = () => {
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    setSent(true);
  };

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>{advisorInitials}</Text>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>Bring this to {firstName}</Text>
          <Text style={styles.subtitle}>{advisorTitle}</Text>
        </View>
      </View>
      {sent ? (
        <View style={styles.sentRow}>
          <Ionicons name="checkmark-circle" size={17} color={colors.allworthAccent} />
          <Text style={styles.sentText}>Flagged for your next session with {firstName}</Text>
        </View>
      ) : (
        <View style={styles.buttons}>
          <HandoffButton label="Message" filled onPress={send} />
          <HandoffButton label="Schedule" onPress={send} />
        </View>
      )}
    </View>
  );
}

function HandoffButton({ label, filled, onPress }: { label: string; filled?: boolean; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: filled ? colors.allworthAccent : "rgba(62,113,183,0.12)" },
        pressed && { opacity: 0.85 },
      ]}
    >
      <Text style={[styles.buttonText, { color: filled ? "#fff" : colors.allworthAccent }]}>{label}</Text>
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
  avatarText: { color: "#fff", fontSize: 16, fontWeight: "600" },
  title: { fontSize: 17, fontWeight: "600", color: colors.inkPrimary },
  subtitle: { fontSize: 13, color: colors.inkSecondary, marginTop: 2 },
  buttons: { flexDirection: "row", gap: 10 },
  button: { flex: 1, paddingVertical: 10, borderRadius: 10, alignItems: "center" },
  buttonText: { fontSize: 15, fontWeight: "600" },
  sentRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  sentText: { fontSize: 15, color: colors.allworthAccent },
});
