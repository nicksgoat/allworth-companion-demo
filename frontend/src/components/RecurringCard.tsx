import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import React, { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { card, colors, fonts, usd } from "../theme";
import { HairlineDivider } from "./Rows";

// Recurring deposits aren't in the backend seed — demo constants, kept
// consistent with the seed accounts (Trust Brokerage, Roth IRA).
const PLANS = [
  {
    id: "trust",
    label: "Trust Brokerage",
    caption: "Auto-invest · monthly on the 1st",
    amount: 3000,
  },
  { id: "roth", label: "Roth IRA", caption: "On track to max your annual limit", amount: 667 },
];

// Glance rule: the header row (total + next deposit) is the summary; the
// per-plan rows and ask affordance unfold on tap.
export function RecurringCard({ onAsk }: { onAsk: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const monthlyTotal = PLANS.reduce((sum, p) => sum + p.amount, 0);
  const now = new Date();
  const next = new Date(now.getFullYear(), now.getMonth() + 1, 1);
  const nextLabel = next.toLocaleDateString("en-US", { month: "short", day: "numeric" });

  const toggle = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setExpanded((v) => !v);
  };

  return (
    <View style={styles.card}>
      <Pressable
        onPress={toggle}
        style={({ pressed }) => [styles.header, pressed && { opacity: 0.7 }]}
      >
        <View style={styles.icon}>
          <Ionicons name="repeat" size={20} color={colors.allworthAccent} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>Automatic investing</Text>
          <Text style={styles.subtitle}>Next deposit {nextLabel}</Text>
        </View>
        <Text style={styles.total}>{usd(monthlyTotal)}/mo</Text>
        <Ionicons
          name={expanded ? "chevron-up" : "chevron-down"}
          size={14}
          color={colors.inkTertiary}
        />
      </Pressable>

      {expanded ? (
        <>
          {PLANS.map((plan) => (
            <React.Fragment key={plan.id}>
              <HairlineDivider />
              <View style={styles.row}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowLabel}>{plan.label}</Text>
                  <Text style={styles.rowCaption}>{plan.caption}</Text>
                </View>
                <Text style={styles.rowAmount}>{usd(plan.amount)}/mo</Text>
              </View>
            </React.Fragment>
          ))}

          <Pressable
            onPress={onAsk}
            style={({ pressed }) => [styles.ask, pressed && { opacity: 0.85 }]}
          >
            <Text style={styles.askText}>Could I be investing more each month?</Text>
          </Pressable>
        </>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { ...card, padding: 16, gap: 12 },
  header: { flexDirection: "row", alignItems: "center", gap: 12 },
  icon: { width: 28, alignItems: "center" },
  title: { fontSize: 17, fontFamily: fonts.sansBold, color: colors.inkPrimary },
  subtitle: { fontSize: 13, fontFamily: fonts.sans, color: colors.inkTertiary, marginTop: 2 },
  total: {
    fontSize: 17,
    fontFamily: fonts.sansBold,
    color: colors.inkPrimary,
    fontVariant: ["tabular-nums"],
  },
  row: { flexDirection: "row", alignItems: "center", gap: 12, paddingVertical: 4 },
  rowLabel: { fontSize: 15, fontFamily: fonts.sans, color: colors.inkPrimary },
  rowCaption: { fontSize: 12, fontFamily: fonts.sans, color: colors.inkTertiary, marginTop: 1 },
  rowAmount: {
    fontSize: 15,
    fontFamily: fonts.sansBold,
    color: colors.inkPrimary,
    fontVariant: ["tabular-nums"],
  },
  ask: {
    backgroundColor: "rgba(62,113,183,0.12)",
    paddingVertical: 10,
    borderRadius: 10,
    alignItems: "center",
  },
  askText: { color: colors.allworthAccent, fontSize: 15, fontFamily: fonts.sansBold },
});
