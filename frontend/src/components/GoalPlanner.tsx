import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import React, { useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useApp } from "../state";
import { colors, fonts, radius, space, text, usd } from "../theme";
import type { FundedGoal } from "../types";

// Live goal planner (stakeholder ask: adjustable goals + cash-flow planning
// integrated with chat). One shared implementation drives both the GoalsSheet
// and the chat's goal widget: dial in a monthly amount and timeline, watch the
// projection move, save the plan — the backend merges it into every future
// chat answer and the advisor's brief.

const MONTHLY_GROWTH = 0.06 / 12; // matches the backend's assumed growth rate

export function projectGoal(saved: number, monthly: number, months: number): number {
  let v = saved;
  for (let i = 0; i < months; i++) v = v * (1 + MONTHLY_GROWTH) + monthly;
  return Math.round(v);
}

function roundTo(v: number, step: number): number {
  return Math.max(step, Math.round(v / step) * step);
}

// Dial options are derived from the goal itself: the middle monthly chip is
// roughly what's needed to close the gap, flanked by a lighter and a heavier
// commitment; years bracket the plan horizon.
function dialOptions(goal: FundedGoal) {
  const h = goal.horizonYears ?? 4;
  const years = [...new Set([Math.max(1, h - 1), h, h + 2])];
  const close = goal.monthlyContributionToClose ?? 0;
  const mid = close > 0 ? roundTo(close, 250) : 1000;
  const monthly = [...new Set([roundTo(mid / 2, 250), mid, roundTo(mid * 1.5, 250)])];
  return { years, monthly };
}

export function GoalDials({ goal, onAsk }: { goal: FundedGoal; onAsk?: () => void }) {
  const app = useApp();
  const { years: yearOpts, monthly: monthlyOpts } = useMemo(() => dialOptions(goal), [goal]);
  const [years, setYears] = useState(goal.committedYears ?? goal.horizonYears ?? yearOpts[1]);
  const [monthly, setMonthly] = useState(goal.committedMonthly ?? monthlyOpts[1]);
  const [saved, setSaved] = useState<null | { monthly: number; years: number }>(
    goal.committedMonthly ? { monthly: goal.committedMonthly, years: goal.committedYears ?? 0 } : null,
  );
  const [saving, setSaving] = useState(false);

  const target = goal.target ?? 0;
  const projected = projectGoal(goal.currentFunded ?? 0, monthly, years * 12);
  const pct = target > 0 ? Math.min(1, projected / target) : 0;
  const onTrack = projected >= target;

  const pick = <T,>(setter: (v: T) => void) => (v: T) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setter(v);
  };

  const savePlan = async () => {
    if (saving) return;
    setSaving(true);
    try {
      await app.api.saveGoalPlan(app.clientId, goal.id, { monthly, years });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      setSaved({ monthly, years });
    } catch {}
    setSaving(false);
  };

  const dirty = !saved || saved.monthly !== monthly || saved.years !== years;

  return (
    <View style={{ gap: space[3] }}>
      <Text style={styles.projection}>
        {usd(projected)} <Text style={styles.of}>of {usd(target)} in {years} years</Text>
      </Text>
      <View style={styles.track}>
        <View
          style={[
            styles.fill,
            { width: `${Math.round(pct * 100)}%` },
            { backgroundColor: onTrack ? colors.chartEvergreen : colors.chartPumpkin },
          ]}
        />
      </View>

      <View style={styles.dialRow}>
        <Text style={styles.dialLabel}>Timeline</Text>
        {yearOpts.map((y) => (
          <Pressable
            key={y}
            onPress={() => pick(setYears)(y)}
            style={[styles.chip, years === y && styles.chipActive]}
          >
            <Text style={[styles.chipText, years === y && styles.chipTextActive]}>{y} yr</Text>
          </Pressable>
        ))}
      </View>
      <View style={styles.dialRow}>
        <Text style={styles.dialLabel}>Monthly</Text>
        {monthlyOpts.map((m) => (
          <Pressable
            key={m}
            onPress={() => pick(setMonthly)(m)}
            style={[styles.chip, monthly === m && styles.chipActive]}
          >
            <Text style={[styles.chipText, monthly === m && styles.chipTextActive]}>
              ${m >= 1000 ? `${(m / 1000).toFixed(m % 1000 ? 2 : 0).replace(/\.?0+$/, "")}k` : m}
            </Text>
          </Pressable>
        ))}
      </View>

      <View style={styles.actionRow}>
        <Pressable
          onPress={savePlan}
          disabled={saving || !dirty}
          style={[styles.saveBtn, (saving || !dirty) && { opacity: 0.4 }]}
        >
          <Text style={styles.saveBtnText}>{dirty ? "Save plan" : "Plan saved"}</Text>
        </Pressable>
        {onAsk ? (
          <Pressable onPress={onAsk} style={({ pressed }) => [styles.askBtn, pressed && { opacity: 0.7 }]}>
            <Text style={styles.askBtnText}>Ask in chat</Text>
          </Pressable>
        ) : null}
      </View>

      {saved && !dirty ? (
        <View style={styles.savedRow}>
          <Ionicons name="checkmark-circle" size={15} color={colors.allworthAccent} />
          <Text style={styles.savedText}>
            Saved — your assistant and your advisor both see this plan.
          </Text>
        </View>
      ) : null}

      <Text style={styles.footnote}>
        Assumes the plan{"'"}s growth rate. Adjust the dials, then pressure-test the plan with
        your advisor.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  projection: {
    fontSize: 22,
    fontFamily: fonts.displayMedium,
    color: colors.inkPrimary,
    fontVariant: ["tabular-nums"],
  },
  of: { fontSize: 14, fontFamily: fonts.sans, color: colors.inkSecondary },
  track: { height: 8, borderRadius: 4, backgroundColor: colors.inkFaint, overflow: "hidden" },
  fill: { height: 8, borderRadius: 4 },
  dialRow: { flexDirection: "row", alignItems: "center", gap: space[2] },
  dialLabel: { ...text.caption, width: 60, color: colors.inkTertiary },
  chip: {
    borderWidth: 1,
    borderColor: colors.hairline,
    borderRadius: radius.chip,
    paddingHorizontal: space[3],
    paddingVertical: 6,
  },
  chipActive: { borderColor: colors.allworthAccent, backgroundColor: "rgba(62,113,183,0.08)" },
  chipText: { ...text.bodySm, color: colors.inkSecondary, fontVariant: ["tabular-nums"] },
  chipTextActive: { color: colors.allworthAccent, fontFamily: fonts.sansBold },
  actionRow: { flexDirection: "row", gap: space[2], marginTop: space[1] },
  saveBtn: {
    flex: 1,
    backgroundColor: colors.allworthNavy,
    borderRadius: radius.chip,
    alignItems: "center",
    paddingVertical: space[3],
  },
  saveBtnText: { fontSize: 14, fontFamily: fonts.sansBold, color: "#FFFFFF" },
  askBtn: {
    flex: 1,
    backgroundColor: "rgba(62,113,183,0.12)",
    borderRadius: radius.chip,
    alignItems: "center",
    paddingVertical: space[3],
  },
  askBtnText: { fontSize: 14, fontFamily: fonts.sansBold, color: colors.allworthAccent },
  savedRow: { flexDirection: "row", alignItems: "center", gap: space[1] },
  savedText: { ...text.caption, flex: 1, color: colors.inkSecondary },
  footnote: { ...text.caption, color: colors.inkTertiary, lineHeight: 16 },
});
