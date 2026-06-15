import { Ionicons } from "@expo/vector-icons";
import React, { useMemo, useState } from "react";
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useCountUp } from "../anim";
import { AdvisorHandoffCard } from "../components/AdvisorHandoffCard";
import { RangeChips } from "../components/RangeChips";
import { DisclaimerFooter, HairlineDivider, SectionHeader, SheetHeader } from "../components/Rows";
import { Sparkline } from "../components/Sparkline";
import { useApp } from "../state";
import { positionHistory } from "../synthetic";
import { card, colors, fonts, shortDate, usd } from "../theme";
import type { Account, Position, TaxLot } from "../types";

const RANGES: { label: string; points: number; suffix: string }[] = [
  { label: "3M", points: 4, suffix: "past 3 months" },
  { label: "6M", points: 7, suffix: "past 6 months" },
  { label: "1Y", points: 12, suffix: "past year" },
];

// "$27.40" — lot costs need cents, unlike the rounded usd() used everywhere else
function usdExact(n: number): string {
  return "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function PositionDetailSheet({
  position,
  account,
  lots,
  onClose,
}: {
  position: Position | null;
  account: Account | null;
  lots: TaxLot[];
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
          lots={lots}
          onClose={onClose}
        />
      ) : null}
    </Modal>
  );
}

function PositionDetailContent({
  position,
  account,
  lots,
  onClose,
}: {
  position: Position;
  account: Account | null;
  lots: TaxLot[];
  onClose: () => void;
}) {
  const app = useApp();
  const [range, setRange] = useState("1Y");
  const animatedValue = useCountUp(position.value);

  const history = useMemo(() => positionHistory(position), [position]);
  const spec = RANGES.find((r) => r.label === range) ?? RANGES[RANGES.length - 1];
  const slice = history.slice(-spec.points);
  const diff = slice.length >= 2 ? slice[slice.length - 1].value - slice[0].value : 0;

  const basis = lots.reduce((sum, lot) => sum + lot.qty * lot.costPerShare, 0);
  const gain = position.value - basis;
  const gainPct = basis ? Math.round((gain / basis) * 100) : 0;
  const hasShortLot = lots.some((lot) => lot.term === "short");

  const ask = () => {
    app.setChatPrefill(
      lots.length
        ? `If I trimmed my ${position.symbol} position, what would the tax impact look like?`
        : `How does my ${position.symbol} holding fit my overall allocation?`,
    );
    app.setSelectedTab("chat");
    onClose();
  };

  return (
    <ScrollView
      style={{ backgroundColor: colors.surfacePrimary }}
      contentContainerStyle={{ padding: 20, gap: 20, paddingTop: 24 }}
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
            {usd(diff)} {spec.suffix}
          </Text>
          <Text style={styles.illustrative}>illustrative</Text>
        </View>
        <Sparkline points={slice} />
        <RangeChips options={RANGES.map((r) => r.label)} selected={range} onSelect={setRange} />
      </View>

      {lots.length ? (
        <View style={styles.card}>
          <SectionHeader>Cost basis & gains</SectionHeader>
          <BasisRow label="Cost basis" value={usd(basis)} />
          <HairlineDivider />
          <BasisRow label="Market value" value={usd(position.value)} />
          <HairlineDivider />
          <BasisRow
            label="Unrealized gain"
            value={`${gain >= 0 ? "+" : ""}${usd(gain)} (${gainPct}%)`}
            color={gain >= 0 ? colors.gain : colors.loss}
          />
        </View>
      ) : (
        <View style={styles.card}>
          <Text style={styles.noLots}>
            Held in a tax-advantaged account — selling here has no capital-gains impact.
          </Text>
        </View>
      )}

      {lots.length ? (
        <View style={{ gap: 4 }}>
          <SectionHeader>Your tax lots</SectionHeader>
          {lots.map((lot, i) => (
            <React.Fragment key={lot.id}>
              {i > 0 ? <HairlineDivider /> : null}
              <LotRow lot={lot} price={position.price} />
            </React.Fragment>
          ))}
          {hasShortLot ? (
            <Text style={styles.shortNote}>
              Short-term lots are taxed at a higher rate — worth asking about before selling.
            </Text>
          ) : null}
        </View>
      ) : null}

      <Pressable onPress={ask} style={({ pressed }) => [styles.cta, pressed && { opacity: 0.85 }]}>
        <Ionicons name="chatbubbles-outline" size={18} color="#fff" />
        <Text style={styles.ctaText}>
          {lots.length ? "Ask about the tax impact" : "Ask how this fits my plan"}
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

function LotRow({ lot, price }: { lot: TaxLot; price: number }) {
  const lotGain = (price - lot.costPerShare) * lot.qty;
  return (
    <View style={styles.lotRow}>
      <View style={{ flex: 1 }}>
        <Text style={styles.lotTitle}>
          {lot.qty.toLocaleString("en-US")} sh · {usdExact(lot.costPerShare)}
        </Text>
        <Text style={styles.lotMeta}>Bought {shortDate(lot.acquired)}</Text>
      </View>
      <View style={{ alignItems: "flex-end", gap: 3 }}>
        <Text style={[styles.lotGain, { color: lotGain >= 0 ? colors.gain : colors.loss }]}>
          {lotGain >= 0 ? "+" : ""}
          {usd(lotGain)}
        </Text>
        <View style={[styles.termBadge, lot.term === "short" && styles.termBadgeShort]}>
          <Text style={[styles.termText, lot.term === "short" && styles.termTextShort]}>
            {lot.term === "short" ? "Short-term" : "Long-term"}
          </Text>
        </View>
      </View>
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
  lotRow: { flexDirection: "row", alignItems: "center", paddingVertical: 10, gap: 12 },
  lotTitle: {
    fontSize: 15,
    fontFamily: fonts.sans,
    color: colors.inkPrimary,
    fontVariant: ["tabular-nums"],
  },
  lotMeta: { fontSize: 13, fontFamily: fonts.sans, color: colors.inkTertiary, marginTop: 2 },
  lotGain: { fontSize: 15, fontFamily: fonts.sansBold, fontVariant: ["tabular-nums"] },
  termBadge: {
    backgroundColor: colors.inkFaint,
    paddingHorizontal: 7,
    paddingVertical: 2,
    borderRadius: 6,
  },
  termBadgeShort: { backgroundColor: "rgba(210,109,55,0.12)" },
  termText: { fontSize: 11, fontFamily: fonts.sansBold, color: colors.inkSecondary },
  termTextShort: { color: colors.attention },
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
