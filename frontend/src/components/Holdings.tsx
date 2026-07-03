import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import React, { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { card, colors, fonts, usd } from "../theme";
import type { Account, Position } from "../types";
import { HairlineDivider } from "./Rows";

// Mirrors the backend concentration nudge rule (>20% of an account in a single
// non-fund position) so row badges and nudge copy always agree.
const FUNDS = new Set(["VTI", "VXUS", "VTEB", "BND", "FXAIX", "FSPSX", "FXNAX", "SPAXX"]);

function isConcentrated(p: Position, accountTotal: number): boolean {
  if (p.assetClass === "cash" || p.symbol === "CASH") return false;
  if (FUNDS.has(p.symbol)) return false;
  return accountTotal > 0 && p.value / accountTotal > 0.2;
}

// Glance rule (DESIGN.md): the account header — name, institution, holding
// count, total — is always visible; the position rows unfold on tap.
export function AccountHoldingsSection({
  account,
  positions,
  onSelect,
  initiallyExpanded = false,
}: {
  account: Account;
  positions: Position[];
  onSelect?: (p: Position) => void;
  initiallyExpanded?: boolean;
}) {
  const [expanded, setExpanded] = useState(initiallyExpanded);
  const accountTotal = positions.reduce((sum, p) => sum + p.value, 0);
  const sorted = [...positions].sort((x, y) => y.value - x.value);

  const toggle = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setExpanded((v) => !v);
  };

  return (
    <View style={styles.card}>
      <Pressable
        onPress={toggle}
        style={({ pressed }) => [styles.cardHeader, pressed && { opacity: 0.7 }]}
      >
        <View style={{ flex: 1 }}>
          <Text style={styles.accountName}>{account.name}</Text>
          <Text style={styles.accountInstitution}>
            {account.institution} · {sorted.length} holding{sorted.length === 1 ? "" : "s"}
          </Text>
        </View>
        <Text style={styles.accountTotal}>{usd(accountTotal)}</Text>
        <Ionicons
          name={expanded ? "chevron-up" : "chevron-down"}
          size={14}
          color={colors.inkTertiary}
        />
      </Pressable>
      {expanded
        ? sorted.map((position) => (
            <React.Fragment key={`${position.accountId}-${position.symbol}`}>
              <HairlineDivider />
              <HoldingRow position={position} accountTotal={accountTotal} onSelect={onSelect} />
            </React.Fragment>
          ))
        : null}
    </View>
  );
}

// Structure-first rows (stakeholder rules): value + share of account, no
// gain/loss pills or price charts at list level. Performance detail lives in
// the tapped-in PositionDetailSheet.
function HoldingRow({
  position,
  accountTotal,
  onSelect,
}: {
  position: Position;
  accountTotal: number;
  onSelect?: (p: Position) => void;
}) {
  const weightPct = accountTotal ? Math.round((position.value / accountTotal) * 100) : 0;
  const concentrated = isConcentrated(position, accountTotal);
  const isCash = position.assetClass === "cash" || position.symbol === "CASH";
  const tappable = onSelect != null && !isCash;

  return (
    <Pressable
      onPress={tappable ? () => onSelect(position) : undefined}
      disabled={!tappable}
      style={({ pressed }) => [styles.row, pressed && { opacity: 0.6 }]}
    >
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={styles.symbol}>{position.symbol}</Text>
        <Text style={styles.name} numberOfLines={1}>
          {position.name}
        </Text>
        {concentrated ? (
          <View style={styles.badge}>
            <Text style={styles.badgeText}>{weightPct}% of account</Text>
          </View>
        ) : null}
      </View>
      <View style={{ alignItems: "flex-end", gap: 2 }}>
        <Text style={styles.value}>{usd(position.value)}</Text>
        {/* Concentrated rows already carry the weight in the attention badge. */}
        {concentrated ? null : (
          <Text style={styles.weightLabel}>{isCash ? "cash" : `${weightPct}% of account`}</Text>
        )}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { ...card, paddingHorizontal: 16, paddingVertical: 6 },
  cardHeader: { flexDirection: "row", alignItems: "center", gap: 12, paddingVertical: 12 },
  accountName: { fontSize: 15, fontFamily: fonts.sansBold, color: colors.inkPrimary },
  accountInstitution: {
    fontSize: 12,
    fontFamily: fonts.sans,
    color: colors.inkTertiary,
    marginTop: 1,
  },
  accountTotal: {
    fontSize: 15,
    fontFamily: fonts.sansBold,
    color: colors.inkSecondary,
    fontVariant: ["tabular-nums"],
  },
  row: { flexDirection: "row", alignItems: "center", paddingVertical: 12, gap: 14 },
  symbol: { fontSize: 16, fontFamily: fonts.sansBold, color: colors.inkPrimary },
  name: { fontSize: 13, fontFamily: fonts.sans, color: colors.inkTertiary, marginTop: 2 },
  badge: {
    alignSelf: "flex-start",
    backgroundColor: "rgba(210,109,55,0.12)",
    paddingHorizontal: 7,
    paddingVertical: 2,
    borderRadius: 6,
    marginTop: 5,
  },
  badgeText: { fontSize: 11, fontFamily: fonts.sansBold, color: colors.attention },
  value: {
    fontSize: 16,
    fontFamily: fonts.sansBold,
    color: colors.inkPrimary,
    fontVariant: ["tabular-nums"],
  },
  weightLabel: {
    fontSize: 12,
    fontFamily: fonts.sans,
    color: colors.inkTertiary,
    fontVariant: ["tabular-nums"],
  },
});
