import { Ionicons } from "@expo/vector-icons";
import React, { useMemo, useState } from "react";
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useCountUp } from "../anim";
import { AdvisorHandoffCard } from "../components/AdvisorHandoffCard";
import { RangeChips } from "../components/RangeChips";
import { DisclaimerFooter, HairlineDivider, SectionHeader, SheetHeader } from "../components/Rows";
import { Sparkline } from "../components/Sparkline";
import { performanceFromSeries } from "../performance";
import { useApp } from "../state";
import { positionHistory } from "../synthetic";
import { card, colors, fonts, usd } from "../theme";
import type { Account, Position } from "../types";

const RANGES: { label: string; points: number; suffix: string }[] = [
  { label: "3M", points: 4, suffix: "past 3 months" },
  { label: "6M", points: 7, suffix: "past 6 months" },
  { label: "1Y", points: 12, suffix: "past year" },
];

// "$27.40" — per-share costs need cents, unlike the rounded usd() used elsewhere
function usdExact(n: number): string {
  return "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function PositionDetailSheet({
  position,
  account,
  onClose,
}: {
  position: Position | null;
  account: Account | null;
  onClose: () => void;
}) {
  return (
    <Modal
      visible={position != null}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={onClose}
    >
      {position ? (
        <PositionDetailContent
          position={position}
          account={account}
          onClose={onClose}
        />
      ) : null}
    </Modal>
  );
}

function PositionDetailContent({
  position,
  account,
  onClose,
}: {
  position: Position;
  account: Account | null;
  onClose: () => void;
}) {
  const app = useApp();
  const [range, setRange] = useState("1Y");
  const animatedValue = useCountUp(position.value);

  const history = useMemo(() => positionHistory(position), [position]);
  const spec = RANGES.find((r) => r.label === range) ?? RANGES[RANGES.length - 1];
  const slice = history.slice(-spec.points);
  const performance = performanceFromSeries(slice);
  const diff = performance?.gain_loss ?? 0;

  const basis = position.costBasis ?? position.value;
  const gain = position.value - basis;
  const gainPct = basis ? Math.round((gain / basis) * 100) : 0;
  const hasAggregateTaxData = position.costBasis != null;
  const hasShortTermGain = Math.abs(position.shortTermUnrealizedGain ?? 0) > 0.005;

  const ask = () => {
    app.setChatPrefill(
      hasAggregateTaxData
        ? `If I trimmed my ${position.symbol} position, what would the tax impact look like?`
        : `How does my ${position.symbol} holding fit my overall allocation?`,
    );
    app.setSelectedTab("chat");
    onClose();
  };

  return (
    <ScrollView
      style={{ backgroundColor: colors.surfacePrimary }}
      contentContainerStyle={{ padding: 20, gap: 20, paddingTop: 0 }}
    >
      <SheetHeader
        title={account ? `${account.name} · ${account.institution}` : "Holding"}
        onClose={onClose}
      />

      <View style={{ gap: 4 }}>
        <Text style={styles.symbol}>{position.symbol}</Text>
        <Text style={styles.name}>{position.name}</Text>
      </View>

      <View style={{ gap: 2 }}>
        <Text style={styles.value}>{usd(animatedValue)}</Text>
        <Text style={styles.caption}>
          {position.qty.toLocaleString("en-US")} shares · {usdExact(position.price)} each
        </Text>
      </View>

      <View style={{ gap: 12 }}>
        <View style={styles.deltaRow}>
          <Text style={[styles.delta, { color: diff >= 0 ? colors.gain : colors.loss }]}>
            {diff >= 0 ? "+" : ""}
            {usd(diff)} ({diff >= 0 ? "+" : "−"}
            {Math.abs(performance?.return_pct ?? 0).toFixed(1)}%) {spec.suffix}
          </Text>
          <Text style={styles.illustrative}>illustrative</Text>
        </View>
        <Sparkline points={slice} />
        <RangeChips options={RANGES.map((r) => r.label)} selected={range} onSelect={setRange} />
      </View>

      {hasAggregateTaxData ? (
        <View style={styles.card}>
          <SectionHeader>Cost basis & gains</SectionHeader>
          {position.averageCostBasis != null ? (
            <>
              <BasisRow
                label="Average cost basis"
                value={`${usdExact(position.averageCostBasis)} / share`}
              />
              <HairlineDivider />
            </>
          ) : null}
          <BasisRow label="Cost basis" value={usd(basis)} />
          <HairlineDivider />
          <BasisRow label="Market value" value={usd(position.value)} />
          <HairlineDivider />
          <BasisRow
            label="Unrealized gain"
            value={`${gain >= 0 ? "+" : ""}${usd(gain)} (${gainPct}%)`}
            color={gain >= 0 ? colors.gain : colors.loss}
          />
          {Math.abs(position.longTermUnrealizedGain ?? 0) > 0.005 ? (
            <>
              <HairlineDivider />
              <BasisRow
                label="Long-term unrealized gain"
                value={`${(position.longTermUnrealizedGain ?? 0) >= 0 ? "+" : ""}${usd(position.longTermUnrealizedGain ?? 0)}`}
                color={(position.longTermUnrealizedGain ?? 0) >= 0 ? colors.gain : colors.loss}
              />
            </>
          ) : null}
          {hasShortTermGain ? (
            <>
              <HairlineDivider />
              <BasisRow
                label="Short-term unrealized gain"
                value={`${(position.shortTermUnrealizedGain ?? 0) >= 0 ? "+" : ""}${usd(position.shortTermUnrealizedGain ?? 0)}`}
                color={(position.shortTermUnrealizedGain ?? 0) >= 0 ? colors.gain : colors.loss}
              />
            </>
          ) : null}
        </View>
      ) : (
        <View style={styles.card}>
          <Text style={styles.noLots}>
            Held in a tax-advantaged account — selling here has no capital-gains impact.
          </Text>
        </View>
      )}

      {hasShortTermGain ? (
        <Text style={styles.shortNote}>
          Some of this position appears short-term on an aggregate basis, which can change the tax
          estimate before selling.
        </Text>
      ) : null}

      <Pressable onPress={ask} style={({ pressed }) => [styles.cta, pressed && { opacity: 0.85 }]}>
        <Ionicons name="chatbubbles-outline" size={18} color="#fff" />
        <Text style={styles.ctaText}>
          {hasAggregateTaxData ? "Ask about the tax impact" : "Ask how this fits my plan"}
        </Text>
      </Pressable>

      <AdvisorHandoffCard />

      <Text style={styles.chartDisclaimer}>
        Chart and gains are illustrative, generated for this demo — not market data. Past
        performance doesn{"'"}t guarantee future results.
      </Text>
      <DisclaimerFooter />
    </ScrollView>
  );
}

function BasisRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={styles.basisRow}>
      <Text style={styles.basisLabel}>{label}</Text>
      <Text style={[styles.basisValue, color ? { color } : null]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  symbol: { fontSize: 34, fontFamily: fonts.display, color: colors.inkPrimary },
  name: { fontSize: 15, fontFamily: fonts.sans, color: colors.inkSecondary },
  value: {
    fontSize: 40,
    fontFamily: fonts.displayMedium,
    color: colors.inkPrimary,
    fontVariant: ["tabular-nums"],
  },
  caption: {
    fontSize: 14,
    fontFamily: fonts.sans,
    color: colors.inkTertiary,
    fontVariant: ["tabular-nums"],
  },
  deltaRow: { flexDirection: "row", alignItems: "baseline", gap: 8 },
  delta: { fontSize: 15, fontFamily: fonts.sansBold, fontVariant: ["tabular-nums"] },
  illustrative: { fontSize: 11, fontFamily: fonts.sansItalic, color: colors.inkTertiary },
  card: { ...card, padding: 16, gap: 10 },
  basisRow: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 4 },
  basisLabel: { fontSize: 15, fontFamily: fonts.sans, color: colors.inkSecondary },
  basisValue: {
    fontSize: 15,
    fontFamily: fonts.sansBold,
    color: colors.inkPrimary,
    fontVariant: ["tabular-nums"],
  },
  noLots: { fontSize: 14, fontFamily: fonts.sans, color: colors.inkSecondary, lineHeight: 20 },
  shortNote: {
    fontSize: 13,
    fontFamily: fonts.sans,
    color: colors.attention,
    lineHeight: 19,
    paddingTop: 8,
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
  chartDisclaimer: {
    fontSize: 11,
    fontFamily: fonts.sans,
    color: colors.inkTertiary,
    textAlign: "center",
    lineHeight: 16,
  },
});
