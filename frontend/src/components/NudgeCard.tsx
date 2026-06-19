import { Ionicons } from "@expo/vector-icons";
import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { card, colors, fonts } from "../theme";
import type { Nudge } from "../types";

export function iconFor(type: string): keyof typeof Ionicons.glyphMap {
  switch (type) {
    case "spending":
      return "trending-up";
    case "concentration":
      return "pie-chart-outline";
    default:
      return "bulb-outline";
  }
}

// Severity → accent colour + short tag. attention = act on this; info = FYI.
export function severityFor(severity: string): { color: string; label: string } {
  if (severity === "attention") return { color: colors.attention, label: "Attention" };
  return { color: colors.chartSky, label: "Insight" };
}

// Leading percentage in the headline ("18% over plan" → 18, "54% of the account" → 54).
export function leadingPct(headline: string): number | null {
  const m = headline.match(/(\d+(?:\.\d+)?)\s*%/);
  return m ? parseFloat(m[1]) : null;
}

const PLAN_MARK = 100 / 1.5; // plan baseline sits at 66.7% of the spending track

// A glanceable widget: severity-tinted icon, a tag, the headline metric, and a
// mini bar — concentration fills to its share; spending crosses a "plan" mark.
export function NudgeCard({
  nudge,
  onPress,
  fill,
}: {
  nudge: Nudge;
  onPress: () => void;
  fill?: boolean;
}) {
  const sev = severityFor(nudge.severity);
  const pct = leadingPct(nudge.headline);
  const tint = sev.color + "1A"; // ~10% alpha
  const isSpending = nudge.type === "spending";
  // spending: actual is (100+pct)% of plan on a track scaled to 1.5× plan, so the
  // fill visibly crosses the plan mark. concentration/info: fill straight to pct.
  const barFill =
    pct == null ? 0 : isSpending ? Math.min(100, (100 + pct) / 1.5) : Math.min(100, pct);

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [styles.card, fill && { flex: 1 }, pressed && { opacity: 0.9 }]}
    >
      <View style={styles.header}>
        <View style={[styles.iconChip, { backgroundColor: tint }]}>
          <Ionicons name={iconFor(nudge.type)} size={18} color={sev.color} />
        </View>
        <View style={[styles.tag, { backgroundColor: tint }]}>
          <Text style={[styles.tagText, { color: sev.color }]}>{sev.label}</Text>
        </View>
      </View>

      <Text style={[styles.metric, { color: sev.color }]}>{nudge.headline}</Text>
      <Text style={styles.title} numberOfLines={2}>
        {nudge.title}
      </Text>

      {pct != null ? (
        <View style={styles.barTrack}>
          <View style={[styles.barFill, { width: `${barFill}%`, backgroundColor: sev.color }]} />
          {isSpending ? <View style={[styles.planMark, { left: `${PLAN_MARK}%` }]} /> : null}
        </View>
      ) : null}

      <View style={styles.ctaRow}>
        <Text style={styles.cta}>{nudge.cta}</Text>
        <Ionicons name="arrow-forward" size={15} color={colors.allworthAccent} />
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { ...card, padding: 16, gap: 10 },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  iconChip: {
    width: 36,
    height: 36,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  tag: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999 },
  tagText: { fontSize: 12, fontFamily: fonts.sansBold, letterSpacing: 0.3 },
  metric: {
    fontSize: 25,
    fontFamily: fonts.displayMedium,
    fontVariant: ["tabular-nums"],
  },
  title: { fontSize: 14.5, fontFamily: fonts.sans, color: colors.inkSecondary, lineHeight: 20 },
  barTrack: {
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.inkFaint,
    overflow: "hidden",
    marginTop: 2,
  },
  barFill: { position: "absolute", left: 0, top: 0, bottom: 0, borderRadius: 4 },
  planMark: {
    position: "absolute",
    top: 0,
    bottom: 0,
    width: 2,
    backgroundColor: "rgba(255,255,255,0.85)",
  },
  ctaRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: 2,
  },
  cta: { fontSize: 14.5, fontFamily: fonts.sansBold, color: colors.allworthAccent },
});
