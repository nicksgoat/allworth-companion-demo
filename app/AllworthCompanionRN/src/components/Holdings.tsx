import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { colors, fonts, usd } from "../theme";
import type { Account, Position } from "../types";
import { HairlineDivider, SectionHeader } from "./Rows";

// Mirrors the backend concentration nudge rule (>20% of an account in a single
// non-fund position) so row badges and nudge copy always agree.
const FUNDS = new Set(["VTI", "VXUS", "VTEB", "BND", "FXAIX", "FSPSX", "FXNAX", "SPAXX"]);

function isConcentrated(p: Position, accountTotal: number): boolean {
  if (p.assetClass === "cash" || p.symbol === "CASH") return false;
  if (FUNDS.has(p.symbol)) return false;
  return accountTotal > 0 && p.value / accountTotal > 0.2;
}

export function AccountHoldingsSection({
  account,
  positions,
}: {
  account: Account;
  positions: Position[];
}) {
  const accountTotal = positions.reduce((sum, p) => sum + p.value, 0);
  const sorted = [...positions].sort((x, y) => y.value - x.value);

  return (
    <View>
      <View style={styles.sectionRow}>
        <SectionHeader>{`${account.name} · ${account.institution}`}</SectionHeader>
        <Text style={styles.sectionCaption}>{usd(accountTotal)}</Text>
      </View>
      {sorted.map((position, i) => (
        <React.Fragment key={`${position.accountId}-${position.symbol}`}>
          {i > 0 ? <HairlineDivider /> : null}
          <HoldingRow position={position} accountTotal={accountTotal} />
        </React.Fragment>
      ))}
    </View>
  );
}

function HoldingRow({ position, accountTotal }: { position: Position; accountTotal: number }) {
  const weightPct = accountTotal ? Math.round((position.value / accountTotal) * 100) : 0;
  const concentrated = isConcentrated(position, accountTotal);

  return (
    <View style={styles.row}>
      <View style={{ flex: 1 }}>
        <View style={styles.symbolRow}>
          <Text style={styles.symbol}>{position.symbol}</Text>
          {concentrated ? (
            <View style={styles.badge}>
              <Text style={styles.badgeText}>{weightPct}% of account</Text>
            </View>
          ) : null}
        </View>
        <Text style={styles.name} numberOfLines={1}>
          {position.name}
        </Text>
      </View>
      <View style={{ alignItems: "flex-end" }}>
        <Text style={styles.value}>{usd(position.value)}</Text>
        <Text style={styles.weight}>{weightPct}%</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  sectionRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingBottom: 4,
    gap: 12,
  },
  sectionCaption: {
    fontSize: 13,
    fontFamily: fonts.sans,
    color: colors.inkSecondary,
    fontVariant: ["tabular-nums"],
  },
  row: { flexDirection: "row", alignItems: "center", paddingVertical: 12, gap: 12 },
  symbolRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  symbol: { fontSize: 17, fontFamily: fonts.sans, color: colors.inkPrimary },
  badge: {
    backgroundColor: "rgba(210,109,55,0.12)",
    paddingHorizontal: 7,
    paddingVertical: 2,
    borderRadius: 6,
  },
  badgeText: { fontSize: 11, fontFamily: fonts.sansBold, color: colors.attention },
  name: { fontSize: 13, fontFamily: fonts.sans, color: colors.inkTertiary, marginTop: 2 },
  value: {
    fontSize: 17,
    fontFamily: fonts.sansBold,
    color: colors.inkPrimary,
    fontVariant: ["tabular-nums"],
  },
  weight: {
    fontSize: 13,
    fontFamily: fonts.sans,
    color: colors.inkTertiary,
    marginTop: 2,
    fontVariant: ["tabular-nums"],
  },
});
