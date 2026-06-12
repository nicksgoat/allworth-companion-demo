import { Ionicons } from "@expo/vector-icons";
import React, { useMemo } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { card, colors, fonts } from "../theme";
import type { AssetClass, Position } from "../types";

// Plan risk target ("60/40 growth & income") lives in the advisor plan tool,
// not exposed over HTTP — hardcoded demo constant per golden API contract.
export const PLAN_TARGET = { equity: 0.6, income: 0.4 };

// Charts draw from the brand secondary palette (deck p.7)
export const ALLOCATION_CLASSES: { key: AssetClass; label: string; color: string }[] = [
  { key: "us_equity", label: "US stocks", color: colors.chartNightBlue },
  { key: "intl_equity", label: "International stocks", color: colors.chartSky },
  { key: "bond", label: "Bonds", color: colors.chartGold },
  { key: "muni_bond", label: "Municipal bonds", color: colors.chartEvergreen },
  { key: "cash", label: "Cash", color: colors.chartLightGray },
];

export function AllocationCard({
  positions,
  onAskRebalance,
  onSelectClass,
}: {
  positions: Position[];
  onAskRebalance: () => void;
  onSelectClass?: (c: AssetClass) => void;
}) {
  const a = useMemo(() => {
    const invested = positions.reduce((sum, p) => sum + p.value, 0);
    const byClass = {} as Record<AssetClass, number>;
    for (const c of ALLOCATION_CLASSES) byClass[c.key] = 0;
    for (const p of positions) byClass[p.assetClass] += p.value;
    const pct = (k: AssetClass) => (invested ? byClass[k] / invested : 0);
    const equityPct = pct("us_equity") + pct("intl_equity");
    // Cash counted on the defensive side — consistent with the income sleeve of a 60/40 plan
    const incomePct = pct("bond") + pct("muni_bond") + pct("cash");
    const driftPts = Math.round((equityPct - PLAN_TARGET.equity) * 100);
    return { byClass, pct, equityPct, incomePct, driftPts };
  }, [positions]);

  return (
    <View style={styles.card}>
      <View style={styles.segmentBar}>
        {ALLOCATION_CLASSES.map((c) =>
          a.byClass[c.key] > 0 ? (
            <View key={c.key} style={{ flex: a.byClass[c.key], backgroundColor: c.color }} />
          ) : null,
        )}
      </View>

      <View style={styles.legend}>
        {ALLOCATION_CLASSES.map((c) =>
          a.byClass[c.key] > 0 ? (
            <Pressable
              key={c.key}
              onPress={onSelectClass ? () => onSelectClass(c.key) : undefined}
              disabled={!onSelectClass}
              style={({ pressed }) => [styles.legendRow, pressed && { opacity: 0.6 }]}
            >
              <View style={[styles.legendDot, { backgroundColor: c.color }]} />
              <Text style={styles.legendLabel}>{c.label}</Text>
              <Text style={styles.legendPct}>{Math.round(a.pct(c.key) * 100)}%</Text>
              {onSelectClass ? (
                <Ionicons name="chevron-forward" size={14} color={colors.inkTertiary} />
              ) : null}
            </Pressable>
          ) : null,
        )}
      </View>

      <View style={styles.driftSection}>
        <MixBar
          label="Current"
          equityPct={a.equityPct}
          caption={`${Math.round(a.equityPct * 100)}% stocks · ${Math.round(a.incomePct * 100)}% bonds & cash`}
        />
        <MixBar
          label="Plan target"
          equityPct={PLAN_TARGET.equity}
          caption={`${Math.round(PLAN_TARGET.equity * 100)}% · ${Math.round(PLAN_TARGET.income * 100)}%`}
        />
      </View>

      {Math.abs(a.driftPts) >= 3 ? (
        <Text style={styles.driftCallout}>
          About {Math.abs(a.driftPts)} points {a.driftPts > 0 ? "overweight" : "underweight"} stocks
          vs your 60/40 growth & income plan.
        </Text>
      ) : null}

      <Pressable
        onPress={onAskRebalance}
        style={({ pressed }) => [styles.askButton, pressed && { opacity: 0.85 }]}
      >
        <Text style={styles.askButtonText}>Ask Allworth AI about rebalancing</Text>
      </Pressable>
    </View>
  );
}

function MixBar({
  label,
  equityPct,
  caption,
}: {
  label: string;
  equityPct: number;
  caption: string;
}) {
  return (
    <View style={{ gap: 5 }}>
      <View style={styles.mixLabelRow}>
        <Text style={styles.mixLabel}>{label}</Text>
        <Text style={styles.mixCaption}>{caption}</Text>
      </View>
      <View style={styles.mixBar}>
        <View style={{ flex: equityPct, backgroundColor: colors.chartNightBlue }} />
        <View style={{ flex: 1 - equityPct, backgroundColor: colors.chartGold }} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { ...card, padding: 16, gap: 14 },
  segmentBar: {
    flexDirection: "row",
    height: 12,
    borderRadius: 6,
    overflow: "hidden",
  },
  legend: { gap: 6 },
  legendRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  legendDot: { width: 8, height: 8, borderRadius: 4 },
  legendLabel: { flex: 1, fontSize: 14, fontFamily: fonts.sans, color: colors.inkSecondary },
  legendPct: {
    fontSize: 14,
    fontFamily: fonts.sansBold,
    color: colors.inkPrimary,
    fontVariant: ["tabular-nums"],
  },
  driftSection: { gap: 12, paddingTop: 2 },
  mixLabelRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  mixLabel: { fontSize: 13, fontFamily: fonts.sansBold, color: colors.inkPrimary },
  mixCaption: {
    fontSize: 13,
    fontFamily: fonts.sans,
    color: colors.inkSecondary,
    fontVariant: ["tabular-nums"],
  },
  mixBar: { flexDirection: "row", height: 8, borderRadius: 4, overflow: "hidden" },
  driftCallout: { fontSize: 14, fontFamily: fonts.sans, color: colors.attention, lineHeight: 20 },
  askButton: {
    backgroundColor: "rgba(62,113,183,0.12)",
    paddingVertical: 10,
    borderRadius: 10,
    alignItems: "center",
  },
  askButtonText: { color: colors.allworthAccent, fontSize: 15, fontFamily: fonts.sansBold },
});
