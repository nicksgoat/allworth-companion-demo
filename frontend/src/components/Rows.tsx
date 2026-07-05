import { Ionicons } from "@expo/vector-icons";
import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { colors, fonts, sectionHeader, shortDate, usd } from "../theme";
import type { Account, Dashboard, LearnedFact, MeetingNote } from "../types";

export function SectionHeader({ children }: { children: React.ReactNode }) {
  return <Text style={styles.sectionHeader}>{children}</Text>;
}

// The shared navy sheet header (Tier 3 of the navy header system): a full-bleed
// solid-navy bar with a white title (+ optional subtitle) and a white close
// chip, sitting flush at the top of a sheet. Assumes the sheet's scroll content
// uses a 20px horizontal gutter and `paddingTop: 0` (so this bleeds to the sheet
// edges). Pass `right` to replace the close chip (e.g. a "Done" text button).
// Sheets have no swipe-to-dismiss on web, so every sheet needs a visible close.
export function SheetHeader({
  title,
  subtitle,
  onClose,
  right,
}: {
  title: string;
  subtitle?: string;
  onClose?: () => void;
  right?: React.ReactNode;
}) {
  return (
    <View style={styles.sheetHeader}>
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={styles.sheetTitle} numberOfLines={1}>
          {title}
        </Text>
        {subtitle ? (
          <Text style={styles.sheetSubtitle} numberOfLines={1}>
            {subtitle}
          </Text>
        ) : null}
      </View>
      {right ??
        (onClose ? (
          <Pressable
            onPress={onClose}
            hitSlop={8}
            style={({ pressed }) => [styles.sheetClose, pressed && { opacity: 0.6 }]}
          >
            <Ionicons name="close" size={20} color="#FFFFFF" />
          </Pressable>
        ) : null)}
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

export function MeetingNoteRow({ note }: { note: MeetingNote }) {
  return (
    <View style={styles.factRow}>
      <View style={styles.noteTitleRow}>
        <Text style={styles.noteTitle}>{note.title}</Text>
        <Text style={styles.noteDate}>{shortDate(note.date)}</Text>
      </View>
      <Text style={styles.noteSummary} numberOfLines={2}>
        {note.summary}
      </Text>
      <Text style={styles.factMeta}>With {note.advisor}</Text>
    </View>
  );
}

export function DisclaimerFooter({ status }: { status?: Dashboard["dataStatus"] }) {
  // Fold the "Synthetic · As of…" data-status indication into the footer so the
  // compliance information stays present without competing with the net-worth
  // number under the hero.
  const asOf = status?.isStale ? "stale data" : status?.asOf ? `as of ${status.asOf}` : null;
  return (
    <Text style={styles.disclaimer}>
      Educational information, not investment advice. Allworth Financial demo — synthetic data
      {asOf ? `, ${asOf}` : ""}.
    </Text>
  );
}

const styles = StyleSheet.create({
  sectionHeader: { ...sectionHeader },
  sheetHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    backgroundColor: colors.chartNightBlue,
    // Bleed to the sheet edges (sheets use a 20px gutter + paddingTop: 0).
    marginHorizontal: -20,
    paddingHorizontal: 20,
    paddingTop: 18,
    paddingBottom: 16,
    borderBottomLeftRadius: 22,
    borderBottomRightRadius: 22,
  },
  sheetTitle: { fontSize: 17, fontFamily: fonts.sansBold, color: "#FFFFFF" },
  sheetSubtitle: { fontSize: 13, fontFamily: fonts.sans, color: "rgba(255,255,255,0.72)" },
  sheetClose: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: "rgba(255,255,255,0.16)",
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
  noteTitleRow: { flexDirection: "row", alignItems: "baseline", gap: 10 },
  noteTitle: { flex: 1, fontSize: 16, fontFamily: fonts.sansBold, color: colors.inkPrimary },
  noteDate: { fontSize: 13, fontFamily: fonts.sans, color: colors.inkTertiary },
  noteSummary: {
    fontSize: 15,
    fontFamily: fonts.sans,
    color: colors.inkSecondary,
    lineHeight: 21,
  },
  disclaimer: {
    fontSize: 11,
    fontFamily: fonts.sans,
    color: colors.inkTertiary,
    textAlign: "center",
  },
});
