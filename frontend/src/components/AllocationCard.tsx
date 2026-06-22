import { Ionicons } from "@expo/vector-icons";
import React, { useEffect, useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import Svg, { Circle, G } from "react-native-svg";
import { card, colors, fonts, usd } from "../theme";
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

// Chunky, rounded, gapped donut — the Acorns "Your Portfolio" treatment. Each
// slice is a round-capped arc with real gaps between it and its neighbours.
function DonutChart({
  segments,
  size,
  thickness,
}: {
  segments: { value: number; color: string }[];
  size: number;
  thickness: number;
}) {
  const r = (size - thickness) / 2;
  const circ = 2 * Math.PI * r;
  const total = segments.reduce((s, x) => s + x.value, 0) || 1;
  const gap = circ * 0.012; // hairline separation — a cohesive ring, not floating blobs

  // Clockwise draw-on sweep, matching the line charts' left-to-right reveal.
  const [progress, setProgress] = useState(0);
  useEffect(() => {
    const start = Date.now();
    const duration = 900;
    let raf = 0;
    const tick = () => {
      const t = Math.min(1, (Date.now() - start) / duration);
      setProgress(1 - Math.pow(1 - t, 3));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [segments.length]);

  const front = progress * circ; // arc length the sweep has reached
  // Precompute each slice's length and start offset purely (no mutated accumulator).
  const segLens = segments.map((s) => (s.value / total) * circ);
  const offsets = segLens.map((_, i) => segLens.slice(0, i).reduce((a, b) => a + b, 0));
  return (
    <Svg width={size} height={size}>
      <G transform={`rotate(-90 ${size / 2} ${size / 2})`}>
        {segments.map((seg, i) => {
          const segLen = segLens[i];
          const offset = offsets[i];
          const full = Math.max(0.5, segLen - gap);
          const drawn = Math.max(0, Math.min(full, front - offset)); // reveal up to the sweep front
          return drawn > 0 ? (
            <Circle
              key={i}
              cx={size / 2}
              cy={size / 2}
              r={r}
              stroke={seg.color}
              strokeWidth={thickness}
              strokeLinecap="butt"
              fill="none"
              strokeDasharray={`${drawn} ${circ - drawn}`}
              strokeDashoffset={-(offset + gap / 2)}
            />
          ) : null;
        })}
      </G>
    </Svg>
  );
}

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
    const incomePct = pct("bond") + pct("muni_bond") + pct("cash");
    const driftPts = Math.round((equityPct - PLAN_TARGET.equity) * 100);
    return { byClass, pct, equityPct, incomePct, driftPts };
  }, [positions]);

  const present = ALLOCATION_CLASSES.filter((c) => a.byClass[c.key] > 0);
  const donutSegments = present.map((c) => ({ value: a.byClass[c.key], color: c.color }));

  return (
    <View style={styles.card}>
      <View style={styles.donutWrap}>
        <DonutChart segments={donutSegments} size={196} thickness={22} />
        <View style={styles.donutCenter}>
          <Text style={styles.donutCenterValue}>{Math.round(a.equityPct * 100)}%</Text>
          <Text style={styles.donutCenterLabel}>in stocks</Text>
        </View>
      </View>

      <View style={styles.list}>
        {present.map((c, i) => (
          <Pressable
            key={c.key}
            onPress={onSelectClass ? () => onSelectClass(c.key) : undefined}
            disabled={!onSelectClass}
            style={({ pressed }) => [
              styles.row,
              i > 0 && styles.rowDivider,
              pressed && { opacity: 0.6 },
            ]}
          >
            <View style={[styles.pill, { backgroundColor: c.color }]} />
            <View style={{ flex: 1 }}>
              <Text style={styles.rowLabel} numberOfLines={1}>
                {c.label}
              </Text>
              <Text style={styles.rowSub}>{usd(a.byClass[c.key])}</Text>
            </View>
            <Text style={styles.rowPct}>{Math.round(a.pct(c.key) * 100)}%</Text>
            {onSelectClass ? (
              <Ionicons name="chevron-forward" size={16} color={colors.inkTertiary} />
            ) : null}
          </Pressable>
        ))}
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

const styles = StyleSheet.create({
  card: { ...card, padding: 16, gap: 14 },
  donutWrap: {
    alignSelf: "center",
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 4,
  },
  donutCenter: { position: "absolute", alignItems: "center", pointerEvents: "none" },
  donutCenterValue: {
    fontSize: 38,
    fontFamily: fonts.displayMedium,
    color: colors.allworthNavy,
    fontVariant: ["tabular-nums"],
  },
  donutCenterLabel: {
    fontSize: 14,
    fontFamily: fonts.sans,
    color: colors.inkTertiary,
    marginTop: -2,
  },

  list: { gap: 0 },
  row: { flexDirection: "row", alignItems: "center", gap: 12, paddingVertical: 12 },
  rowDivider: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.hairline },
  pill: { width: 5, height: 34, borderRadius: 3 },
  rowLabel: { fontSize: 16, fontFamily: fonts.sansBold, color: colors.inkPrimary },
  rowSub: {
    fontSize: 13,
    fontFamily: fonts.sans,
    color: colors.inkTertiary,
    marginTop: 1,
    fontVariant: ["tabular-nums"],
  },
  rowPct: {
    fontSize: 16,
    fontFamily: fonts.sansBold,
    color: colors.inkPrimary,
    fontVariant: ["tabular-nums"],
  },

  driftCallout: { fontSize: 14, fontFamily: fonts.sans, color: colors.attention, lineHeight: 20 },
  askButton: {
    backgroundColor: "rgba(62,113,183,0.12)",
    paddingVertical: 12,
    borderRadius: 12,
    alignItems: "center",
  },
  askButtonText: { color: colors.allworthAccent, fontSize: 15, fontFamily: fonts.sansBold },
});
