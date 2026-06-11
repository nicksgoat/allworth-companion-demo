import { Ionicons } from "@expo/vector-icons";
import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { card, colors } from "../theme";
import type { Nudge } from "../types";

function iconFor(type: string): keyof typeof Ionicons.glyphMap {
  switch (type) {
    case "spending":
      return "trending-up";
    case "concentration":
      return "pie-chart-outline";
    default:
      return "bulb-outline";
  }
}

export function NudgeCard({ nudge, onPress }: { nudge: Nudge; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [styles.card, pressed && { opacity: 0.85 }]}
    >
      <Ionicons
        name={iconFor(nudge.type)}
        size={20}
        color={colors.attention}
        style={{ width: 28 }}
      />
      <View style={{ flex: 1, gap: 4 }}>
        <Text style={styles.title}>{nudge.title}</Text>
        <Text style={styles.headline}>{nudge.headline}</Text>
        <Text style={styles.cta}>{nudge.cta}</Text>
      </View>
      <Ionicons
        name="chevron-forward"
        size={15}
        color={colors.inkTertiary}
        style={{ marginTop: 4 }}
      />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { ...card, flexDirection: "row", alignItems: "flex-start", gap: 14, padding: 16 },
  title: { fontSize: 17, fontWeight: "600", color: colors.inkPrimary },
  headline: {
    fontSize: 15,
    fontWeight: "600",
    color: colors.attention,
    fontVariant: ["tabular-nums"],
  },
  cta: { fontSize: 15, color: colors.allworthAccent, paddingTop: 2 },
});
