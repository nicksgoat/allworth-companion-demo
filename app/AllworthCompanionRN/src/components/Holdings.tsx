import React, { useId, useMemo } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import Svg, { Defs, LinearGradient, Path, Stop } from "react-native-svg";
import { positionHistory } from "../synthetic";
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

export function AccountHoldingsSection({
  account,
  positions,
  onSelect,
}: {
  account: Account;
  positions: Position[];
  onSelect?: (p: Position) => void;
}) {
  const accountTotal = positions.reduce((sum, p) => sum + p.value, 0);
  const sorted = [...positions].sort((x, y) => y.value - x.value);

  return (
    <View style={styles.card}>
      <View style={styles.cardHeader}>
        <View style={{ flex: 1 }}>
          <Text style={styles.accountName}>{account.name}</Text>
          <Text style={styles.accountInstitution}>{account.institution}</Text>
        </View>
        <Text style={styles.accountTotal}>{usd(accountTotal)}</Text>
      </View>
      <HairlineDivider />
      {sorted.map((position, i) => (
        <React.Fragment key={`${position.accountId}-${position.symbol}`}>
          {i > 0 ? <HairlineDivider /> : null}
          <HoldingRow position={position} accountTotal={accountTotal} onSelect={onSelect} />
        </React.Fragment>
      ))}
    </View>
  );
}

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

  const { history, pct } = useMemo(() => {
    if (isCash) return { history: [], pct: 0 };
    const h = positionHistory(position);
    const first = h[0].value;
    const last = h[h.length - 1].value;
    return { history: h.map((m) => m.value), pct: first ? ((last - first) / first) * 100 : 0 };
  }, [position, isCash]);

  const up = pct >= 0;

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
      {!isCash ? <MiniSparkline values={history} color={up ? colors.gain : colors.loss} /> : null}
      <View style={{ alignItems: "flex-end", gap: 4 }}>
        <Text style={styles.value}>{usd(position.value)}</Text>
        {!isCash ? (
          <View style={[styles.pill, { backgroundColor: up ? colors.gain : colors.loss }]}>
            <Text style={styles.pillText}>
              {up ? "+" : ""}
              {pct.toFixed(1)}%
            </Text>
          </View>
        ) : (
          <Text style={styles.cashLabel}>cash</Text>
        )}
      </View>
    </Pressable>
  );
}

const SPARK_W = 56;
const SPARK_H = 26;

// Static thumbnail chart, Apple Stocks-style: straight segments + gradient
// wash under the line. No animation — many rows mount at once.
function MiniSparkline({ values, color }: { values: number[]; color: string }) {
  const uid = useId().replace(/:/g, "");
  const fillId = `minispark-${uid}`;

  const { line, area } = useMemo(() => {
    const lo = Math.min(...values);
    const hi = Math.max(...values);
    const span = hi - lo || 1;
    const x = (i: number) => (i / (values.length - 1)) * SPARK_W;
    const y = (v: number) => SPARK_H - 2 - ((v - lo) / span) * (SPARK_H - 4);
    const pts = values.map((v, i) => `${x(i)} ${y(v)}`);
    const l = `M ${pts.join(" L ")}`;
    return { line: l, area: `${l} L ${SPARK_W} ${SPARK_H} L 0 ${SPARK_H} Z` };
  }, [values]);

  if (values.length < 2) return null;
  return (
    <Svg width={SPARK_W} height={SPARK_H}>
      <Defs>
        <LinearGradient id={fillId} x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor={color} stopOpacity={0.22} />
          <Stop offset="1" stopColor={color} stopOpacity={0} />
        </LinearGradient>
      </Defs>
      <Path d={area} fill={`url(#${fillId})`} />
      <Path d={line} stroke={color} strokeWidth={1.5} fill="none" />
    </Svg>
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
  pill: {
    minWidth: 64,
    alignItems: "flex-end",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 7,
  },
  pillText: {
    fontSize: 13,
    fontFamily: fonts.sansBold,
    color: "#fff",
    fontVariant: ["tabular-nums"],
  },
  cashLabel: { fontSize: 12, fontFamily: fonts.sans, color: colors.inkTertiary },
});
