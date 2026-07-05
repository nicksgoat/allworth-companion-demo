import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import React, { useEffect, useState } from "react";
import { ActivityIndicator, Modal, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { GoalDials } from "../components/GoalPlanner";
import { DisclaimerFooter, SectionHeader } from "../components/Rows";
import { useApp } from "../state";
import { card, colors, fonts, space, text, usd } from "../theme";
import type { FundedGoal } from "../types";

// My goals — the real goals from the client's plan (same numbers the chat
// tool computes), each with an adjustable live funding plan. Stakeholder
// asks: adjustable live goals + goal planning integrated with chat.
export function GoalsSheet({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const app = useApp();
  const [goals, setGoals] = useState<FundedGoal[] | null>(null);
  const [summary, setSummary] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    setGoals(null);
    app.api
      .goals(app.clientId)
      .then((res) => {
        if (cancelled) return;
        setGoals(res.goals);
        setSummary(res.summary);
      })
      .catch(() => {
        if (!cancelled) setGoals([]);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  const ask = (goal: FundedGoal) => {
    app.setChatPrefill(`Am I on track for the ${goal.label.toLowerCase()} goal?`);
    app.setSelectedTab("chat");
    onClose();
  };

  const toggle = (id: string) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setExpanded((v) => (v === id ? null : id));
  };

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <ScrollView
        style={{ backgroundColor: colors.surfacePrimary }}
        contentContainerStyle={{ padding: space[5], gap: space[4], paddingBottom: space[8] }}
      >
        <View style={styles.headerRow}>
          <View style={{ flex: 1, gap: 2 }}>
            <Text style={styles.title}>My goals</Text>
            {summary ? <Text style={styles.subtitle}>{summary}</Text> : null}
          </View>
          <Pressable onPress={onClose} hitSlop={8} style={styles.closeBtn}>
            <Ionicons name="close" size={20} color={colors.inkSecondary} />
          </Pressable>
        </View>

        {goals === null ? (
          <ActivityIndicator style={{ paddingTop: 60 }} />
        ) : goals.length === 0 ? (
          <Text style={styles.empty}>
            No goals yet — tell your assistant what you{"'"}re working toward.
          </Text>
        ) : (
          goals.map((goal) =>
            goal.type === "income" ? (
              <View key={goal.id} style={styles.card}>
                <GoalHeader goal={goal} />
                <Text style={styles.incomeDetail}>{goal.detail}</Text>
              </View>
            ) : (
              <View key={goal.id} style={styles.card}>
                <Pressable onPress={() => toggle(goal.id)} style={{ gap: space[2] }}>
                  <GoalHeader goal={goal} expanded={expanded === goal.id} />
                  <View style={styles.track}>
                    <View
                      style={[
                        styles.fill,
                        { width: `${Math.min(100, Math.round(goal.fundedPct ?? 0))}%` },
                        {
                          backgroundColor:
                            goal.status === "on_track" ? colors.chartEvergreen : colors.chartPumpkin,
                        },
                      ]}
                    />
                  </View>
                  <Text style={styles.fundedLine}>
                    {usd(goal.currentFunded ?? 0)} of {usd(goal.target ?? 0)} ·{" "}
                    {goal.committedMonthly
                      ? `your plan: ${usd(goal.committedMonthly)}/mo over ${goal.committedYears} yrs`
                      : goal.status === "on_track"
                        ? `on track over ${goal.horizonYears} yrs`
                        : `~${usd(goal.monthlyContributionToClose ?? 0)}/mo closes the gap`}
                  </Text>
                </Pressable>

                {expanded === goal.id ? (
                  <View style={styles.dialsWrap}>
                    <GoalDials goal={goal} onAsk={() => ask(goal)} />
                  </View>
                ) : null}
              </View>
            ),
          )
        )}

        <SectionHeader>How this works</SectionHeader>
        <Text style={styles.howText}>
          These are the goals in your Allworth plan. Adjust a plan and save it — your assistant
          uses it when you talk about goals, and your advisor sees it too. Decisions stay with you
          and your advisor.
        </Text>

        <DisclaimerFooter />
      </ScrollView>
    </Modal>
  );
}

function GoalHeader({ goal, expanded }: { goal: FundedGoal; expanded?: boolean }) {
  const onTrack = goal.status === "on_track";
  return (
    <View style={styles.goalHeaderRow}>
      <Ionicons name="flag-outline" size={15} color={colors.allworthAccent} />
      <Text style={styles.goalLabel} numberOfLines={1}>
        {goal.label}
      </Text>
      <Text style={[styles.status, { color: onTrack ? colors.gain : colors.attention }]}>
        {onTrack ? "On track" : "Needs attention"}
      </Text>
      {goal.type === "lump_sum" ? (
        <Ionicons name={expanded ? "chevron-up" : "chevron-down"} size={14} color={colors.inkTertiary} />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  headerRow: { flexDirection: "row", alignItems: "flex-start", gap: space[3], paddingTop: space[2] },
  title: { fontSize: 26, fontFamily: fonts.displayMedium, color: colors.allworthNavy },
  subtitle: { ...text.bodySm, color: colors.inkSecondary },
  closeBtn: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.inkFaint,
    alignItems: "center",
    justifyContent: "center",
  },
  card: { ...card, padding: space[4], gap: space[3] },
  goalHeaderRow: { flexDirection: "row", alignItems: "center", gap: space[2] },
  goalLabel: { flex: 1, fontSize: 16, fontFamily: fonts.sansBold, color: colors.inkPrimary },
  status: { fontSize: 12, fontFamily: fonts.sansBold },
  track: { height: 8, borderRadius: 4, backgroundColor: colors.inkFaint, overflow: "hidden" },
  fill: { height: 8, borderRadius: 4 },
  fundedLine: { ...text.bodySm, color: colors.inkSecondary, fontVariant: ["tabular-nums"] },
  incomeDetail: { ...text.bodySm, color: colors.inkSecondary, lineHeight: 19 },
  dialsWrap: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.hairline,
    paddingTop: space[3],
  },
  empty: { ...text.body, color: colors.inkTertiary, textAlign: "center", paddingTop: 40 },
  howText: { ...text.bodySm, color: colors.inkSecondary, lineHeight: 19 },
});
