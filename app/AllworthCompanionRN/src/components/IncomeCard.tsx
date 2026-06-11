import { Ionicons } from "@expo/vector-icons";
import React, { useMemo } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { estimatedAnnualIncome, ytdFraction } from "../synthetic";
import { card, colors, fonts, usd } from "../theme";
import type { Account, Position } from "../types";
import { HairlineDivider } from "./Rows";

export function IncomeCard({
  positions,
  accounts,
  onAsk,
}: {
  positions: Position[];
  accounts: Account[];
  onAsk: () => void;
}) {
  const income = useMemo(() => {
    const fraction = ytdFraction();
    const byAccount = new Map<string, number>();
    let annual = 0;
    for (const p of positions) {
      const a = estimatedAnnualIncome(p);
      annual += a;
      byAccount.set(p.accountId, (byAccount.get(p.accountId) ?? 0) + a * fraction);
    }
    const rows = accounts
      .map((account) => ({ account, ytd: byAccount.get(account.id) ?? 0 }))
      .filter((r) => r.ytd >= 1)
      .sort((x, y) => y.ytd - x.ytd);
    return { ytd: annual * fraction, annual, rows };
  }, [positions, accounts]);

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <View style={styles.icon}>
          <Ionicons name="cash-outline" size={20} color={colors.gain} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>Dividends & income</Text>
          <Text style={styles.subtitle}>Estimated so far this year</Text>
        </View>
        <Text style={styles.total}>{usd(income.ytd)}</Text>
      </View>

      {income.rows.map((row, i) => (
        <React.Fragment key={row.account.id}>
          {i > 0 ? <HairlineDivider /> : null}
          <View style={styles.row}>
            <View style={{ flex: 1 }}>
              <Text style={styles.rowLabel}>{row.account.name}</Text>
              <Text style={styles.rowCaption}>{row.account.institution}</Text>
            </View>
            <Text style={styles.rowAmount}>{usd(row.ytd)}</Text>
          </View>
        </React.Fragment>
      ))}

      <Text style={styles.footnote}>
        Estimated from your current holdings and typical fund yields — about {usd(income.annual)} a
        year at today{"'"}s values. Actuals arrive with statements.
      </Text>

      <Pressable
        onPress={onAsk}
        style={({ pressed }) => [styles.ask, pressed && { opacity: 0.85 }]}
      >
        <Text style={styles.askText}>What income could this generate in retirement?</Text>
      </Pressable>
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
    color: colors.gain,
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
  footnote: { fontSize: 12, fontFamily: fonts.sans, color: colors.inkTertiary, lineHeight: 17 },
  ask: {
    backgroundColor: "rgba(62,113,183,0.12)",
    paddingVertical: 10,
    borderRadius: 10,
    alignItems: "center",
  },
  askText: { color: colors.allworthAccent, fontSize: 15, fontFamily: fonts.sansBold },
});
