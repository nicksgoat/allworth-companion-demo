import { Ionicons } from "@expo/vector-icons";
import React from "react";
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useCountUp } from "../anim";
import { ALLOCATION_CLASSES, PLAN_TARGET } from "../components/AllocationCard";
import { DisclaimerFooter, HairlineDivider, SectionHeader, SheetHeader } from "../components/Rows";
import { useApp } from "../state";
import { colors, fonts, usd } from "../theme";
import type { Account, AssetClass, Position } from "../types";

const GROWTH_CLASSES: AssetClass[] = ["us_equity", "intl_equity"];

export function ClassDetailSheet({
  assetClass,
  positions,
  accounts,
  onClose,
}: {
  assetClass: AssetClass | null;
  positions: Position[];
  accounts: Account[];
  onClose: () => void;
}) {
  return (
    <Modal
      visible={assetClass != null}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={onClose}
    >
      {assetClass ? (
        <ClassDetailContent
          assetClass={assetClass}
          positions={positions}
          accounts={accounts}
          onClose={onClose}
        />
      ) : null}
    </Modal>
  );
}

function ClassDetailContent({
  assetClass,
  positions,
  accounts,
  onClose,
}: {
  assetClass: AssetClass;
  positions: Position[];
  accounts: Account[];
  onClose: () => void;
}) {
  const app = useApp();
  const meta = ALLOCATION_CLASSES.find((c) => c.key === assetClass) ?? ALLOCATION_CLASSES[0];
  const accountById = new Map(accounts.map((a) => [a.id, a]));

  const invested = positions.reduce((sum, p) => sum + p.value, 0);
  const inClass = positions.filter((p) => p.assetClass === assetClass);
  const classTotal = inClass.reduce((sum, p) => sum + p.value, 0);
  const classPct = invested ? Math.round((classTotal / invested) * 100) : 0;
  const sorted = [...inClass].sort((x, y) => y.value - x.value);
  const growth = GROWTH_CLASSES.includes(assetClass);
  const animatedTotal = useCountUp(classTotal);

  const ask = () => {
    app.setChatPrefill(`Is my ${meta.label.toLowerCase()} exposure right for my 60/40 plan?`);
    app.setSelectedTab("chat");
    onClose();
  };

  return (
    <ScrollView
      style={{ backgroundColor: colors.surfacePrimary }}
      contentContainerStyle={{ padding: 20, gap: 20, paddingTop: 24 }}
    >
      <SheetHeader title="Your allocation" onClose={onClose} />

      <View style={{ gap: 6 }}>
        <View style={styles.titleRow}>
          <View style={[styles.dot, { backgroundColor: meta.color }]} />
          <Text style={styles.title}>{meta.label}</Text>
        </View>
        <Text style={styles.value}>{usd(animatedTotal)}</Text>
        <Text style={styles.caption}>{classPct}% of your invested portfolio</Text>
      </View>

      <Text style={styles.planFit}>
        {growth
          ? `Part of the growth side of your ${Math.round(PLAN_TARGET.equity * 100)}/${Math.round(PLAN_TARGET.income * 100)} plan — built for long-term appreciation.`
          : `Part of the income & stability side of your ${Math.round(PLAN_TARGET.equity * 100)}/${Math.round(PLAN_TARGET.income * 100)} plan — there to steady the portfolio.`}
      </Text>

      <View style={{ gap: 4 }}>
        <SectionHeader>{`Holdings in ${meta.label.toLowerCase()}`}</SectionHeader>
        {sorted.map((position, i) => {
          const account = accountById.get(position.accountId);
          const pctOfClass = classTotal ? Math.round((position.value / classTotal) * 100) : 0;
          return (
            <React.Fragment key={`${position.accountId}-${position.symbol}`}>
              {i > 0 ? <HairlineDivider /> : null}
              <View style={styles.row}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.symbol}>{position.symbol}</Text>
                  <Text style={styles.rowMeta} numberOfLines={1}>
                    {account ? `${account.name} · ${account.institution}` : position.name}
                  </Text>
                </View>
                <View style={{ alignItems: "flex-end" }}>
                  <Text style={styles.rowValue}>{usd(position.value)}</Text>
                  <Text style={styles.rowPct}>{pctOfClass}% of class</Text>
                </View>
              </View>
            </React.Fragment>
          );
        })}
      </View>

      <Pressable onPress={ask} style={({ pressed }) => [styles.cta, pressed && { opacity: 0.85 }]}>
        <Ionicons name="chatbubbles-outline" size={18} color="#fff" />
        <Text style={styles.ctaText}>Ask how this fits my plan</Text>
      </Pressable>

      <DisclaimerFooter />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  titleRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  dot: { width: 12, height: 12, borderRadius: 6 },
  title: { fontSize: 28, fontFamily: fonts.display, color: colors.inkPrimary },
  value: {
    fontSize: 40,
    fontFamily: fonts.displayMedium,
    color: colors.inkPrimary,
    fontVariant: ["tabular-nums"],
  },
  caption: { fontSize: 14, fontFamily: fonts.sans, color: colors.inkTertiary },
  planFit: { fontSize: 15, fontFamily: fonts.sans, lineHeight: 22, color: colors.inkSecondary },
  row: { flexDirection: "row", alignItems: "center", paddingVertical: 12, gap: 12 },
  symbol: { fontSize: 17, fontFamily: fonts.sans, color: colors.inkPrimary },
  rowMeta: { fontSize: 13, fontFamily: fonts.sans, color: colors.inkTertiary, marginTop: 2 },
  rowValue: {
    fontSize: 17,
    fontFamily: fonts.sansBold,
    color: colors.inkPrimary,
    fontVariant: ["tabular-nums"],
  },
  rowPct: {
    fontSize: 13,
    fontFamily: fonts.sans,
    color: colors.inkTertiary,
    marginTop: 2,
    fontVariant: ["tabular-nums"],
  },
  cta: {
    flexDirection: "row",
    gap: 8,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.allworthAccent,
    borderRadius: 12,
    paddingVertical: 14,
  },
  ctaText: { color: "#fff", fontSize: 17, fontFamily: fonts.sansBold },
});
