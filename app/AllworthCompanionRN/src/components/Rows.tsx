import { Ionicons } from "@expo/vector-icons";
import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { colors, fonts, sectionHeader, shortDate, usd } from "../theme";
import type { Account, LearnedFact } from "../types";

export function SectionHeader({ children }: { children: string }) {
  return <Text style={styles.sectionHeader}>{children}</Text>;
}

// Sheets have no swipe-to-dismiss on web, so every sheet needs a visible close.
export function SheetHeader({ title, onClose }: { title: string; onClose: () => void }) {
  return (
    <View style={styles.sheetHeader}>
      <View style={{ flex: 1 }}>
        <SectionHeader>{title}</SectionHeader>
      </View>
      <Pressable
        onPress={onClose}
        hitSlop={8}
        style={({ pressed }) => [styles.sheetClose, pressed && { opacity: 0.6 }]}
      >
        <Ionicons name="close" size={18} color={colors.inkSecondary} />
      </Pressable>
    </View>
  );
}

export function HairlineDivider() {
  return <View style={styles.hairline} />;
}

export function AccountRow({ account }: { account: Account }) {
  return (
    <View style={styles.accountRow}>
      <View style={{ flex: 1 }}>
        <Text style={styles.accountName}>{account.name}</Text>
        <Text style={styles.accountInstitution}>{account.institution}</Text>
      </View>
      <Text style={[styles.accountBalance, account.balance < 0 && { color: colors.loss }]}>
        {usd(account.balance)}
      </Text>
    </View>
  );
}

export function LearnedFactRow({ fact }: { fact: LearnedFact }) {
  return (
    <View style={styles.factRow}>
      <Text style={styles.factText}>{fact.fact}</Text>
      {fact.source_quote ? (
        <View style={styles.quoteRow}>
          <View style={styles.quoteBar} />
          <Text style={styles.quoteText}>“{fact.source_quote}”</Text>
        </View>
      ) : null}
      <Text style={styles.factMeta}>
        Learned {shortDate(fact.learned_at)} · from your conversation
      </Text>
    </View>
  );
}

export function DisclaimerFooter() {
  return (
    <Text style={styles.disclaimer}>
      Educational information, not investment advice. Allworth Financial demo — synthetic data.
    </Text>
  );
}

const styles = StyleSheet.create({
  sectionHeader: { ...sectionHeader },
  sheetHeader: { flexDirection: "row", alignItems: "center", gap: 12 },
  sheetClose: {
    width: 30,
    height: 30,
    borderRadius: 15,
    backgroundColor: colors.inkFaint,
    alignItems: "center",
    justifyContent: "center",
  },
  hairline: { height: StyleSheet.hairlineWidth, backgroundColor: colors.hairline },
  accountRow: { flexDirection: "row", alignItems: "center", paddingVertical: 12, gap: 12 },
  accountName: { fontSize: 17, fontFamily: fonts.sans, color: colors.inkPrimary },
  accountInstitution: {
    fontSize: 13,
    fontFamily: fonts.sans,
    color: colors.inkTertiary,
    marginTop: 2,
  },
  accountBalance: {
    fontSize: 17,
    fontFamily: fonts.sansBold,
    color: colors.inkPrimary,
    fontVariant: ["tabular-nums"],
  },
  factRow: { paddingVertical: 12, gap: 8 },
  factText: { fontSize: 17, fontFamily: fonts.sans, color: colors.inkPrimary, lineHeight: 23 },
  quoteRow: { flexDirection: "row", gap: 8 },
  quoteBar: { width: 2, borderRadius: 1, backgroundColor: colors.hairline },
  quoteText: {
    flex: 1,
    fontSize: 15,
    fontFamily: fonts.sansItalic,
    color: colors.inkSecondary,
    lineHeight: 21,
  },
  factMeta: { fontSize: 13, fontFamily: fonts.sans, color: colors.inkTertiary },
  disclaimer: {
    fontSize: 11,
    fontFamily: fonts.sans,
    color: colors.inkTertiary,
    textAlign: "center",
  },
});
