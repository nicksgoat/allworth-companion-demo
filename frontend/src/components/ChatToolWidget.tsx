import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import React, { useState } from "react";
import {
  LayoutChangeEvent,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Svg, { Path } from "react-native-svg";
import { FadeScaleIn } from "../anim";
import { card, colors, fonts, usd } from "../theme";
import type { ToolWidget } from "../types";
import { AllworthMark } from "./Wordmark";

// ─── Shape detection ────────────────────────────────────────────────────────
// We route by the result's shape rather than the tool name, so it's robust to
// which tool the model picks (run_retirement_projection vs simulate, etc.).
function isProjection(r: any): boolean {
  return r && Array.isArray(r.pathSnapshots) && typeof r.successRate === "number";
}
function isRebalance(r: any): boolean {
  return r && Array.isArray(r.trades) && r.target_allocation;
}

function successColor(rate: number, onDark: boolean): string {
  if (rate >= 90) return onDark ? colors.gainOnDark : colors.gain;
  if (rate >= 70) return colors.chartGold;
  return onDark ? colors.lossOnDark : colors.loss;
}

const SLICE_COLORS = [
  colors.chartNightBlue,
  colors.chartSky,
  colors.chartGold,
  colors.chartEvergreen,
  colors.chartPumpkin,
  colors.allworthAccent,
];

// ─── Monte-Carlo fan chart (the cone of uncertainty) ────────────────────────
function FanChart({
  snapshots,
  height,
  onDark,
}: {
  snapshots: any[];
  height: number;
  onDark: boolean;
}) {
  const [w, setW] = useState(0);
  if (!snapshots || snapshots.length < 2) return null;
  const lo = Math.min(...snapshots.map((s) => s.p5));
  const hi = Math.max(...snapshots.map((s) => s.p95));
  const pad = (hi - lo) * 0.08 || 1;
  const yMin = Math.max(0, lo - pad);
  const yMax = hi + pad;
  const x = (i: number) => (i / (snapshots.length - 1)) * w;
  const y = (v: number) => height - ((v - yMin) / (yMax - yMin)) * height;
  const xs = snapshots.map((_, i) => x(i));
  const yOf = (k: string) => snapshots.map((s) => y(s[k]));
  const band = (up: number[], low: number[]) => {
    let d = `M ${xs[0].toFixed(1)} ${up[0].toFixed(1)}`;
    for (let i = 1; i < xs.length; i++) d += ` L ${xs[i].toFixed(1)} ${up[i].toFixed(1)}`;
    for (let i = xs.length - 1; i >= 0; i--) d += ` L ${xs[i].toFixed(1)} ${low[i].toFixed(1)}`;
    return d + " Z";
  };
  const med = yOf("median");
  const medLine = "M " + xs.map((xi, i) => `${xi.toFixed(1)} ${med[i].toFixed(1)}`).join(" L ");
  const fill = onDark ? "#FFFFFF" : colors.allworthAccent;
  const line = onDark ? "#FFFFFF" : colors.allworthNavy;

  return (
    <View style={{ height }} onLayout={(e: LayoutChangeEvent) => setW(e.nativeEvent.layout.width)}>
      {w > 0 ? (
        <Svg width={w} height={height}>
          <Path d={band(yOf("p95"), yOf("p5"))} fill={fill} fillOpacity={onDark ? 0.14 : 0.1} />
          <Path d={band(yOf("p75"), yOf("p25"))} fill={fill} fillOpacity={onDark ? 0.26 : 0.22} />
          <Path
            d={medLine}
            stroke={line}
            strokeWidth={2.5}
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </Svg>
      ) : null}
    </View>
  );
}

// ─── Full-screen scaffold (navy hero modal, shared by both details) ─────────
function DetailModal({
  visible,
  onClose,
  title,
  children,
}: {
  visible: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}) {
  const insets = useSafeAreaInsets();
  return (
    <Modal
      visible={visible}
      animationType="slide"
      presentationStyle="fullScreen"
      onRequestClose={onClose}
    >
      <View style={[styles.modal, { paddingTop: insets.top + 6 }]}>
        <View style={styles.modalTop}>
          <Pressable onPress={onClose} hitSlop={12}>
            <Ionicons name="close" size={26} color="#FFFFFF" />
          </Pressable>
          <Text style={styles.modalTitle}>{title}</Text>
          <AllworthMark size={22} color="#FFFFFF" />
        </View>
        <ScrollView
          contentContainerStyle={{ padding: 20, paddingBottom: insets.bottom + 28, gap: 22 }}
          showsVerticalScrollIndicator={false}
        >
          {children}
        </ScrollView>
      </View>
    </Modal>
  );
}

function DanaCta() {
  const [sent, setSent] = useState(false);
  if (sent) {
    return (
      <View style={[styles.cta, styles.ctaSent]}>
        <Ionicons name="checkmark-circle" size={18} color={colors.gainOnDark} />
        <Text style={[styles.ctaText, { color: "#FFFFFF" }]}>
          Flagged for Dana — she{"'"}ll follow up
        </Text>
      </View>
    );
  }
  return (
    <Pressable
      onPress={() => {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        setSent(true);
      }}
      style={({ pressed }) => [styles.cta, pressed && { opacity: 0.85 }]}
    >
      <Ionicons name="chatbubble-ellipses" size={18} color={colors.allworthNavy} />
      <Text style={styles.ctaText}>Bring this to Dana</Text>
    </Pressable>
  );
}

// ─── Monte Carlo ────────────────────────────────────────────────────────────
function ProjectionCard({ result, onOpen }: { result: any; onOpen: () => void }) {
  const rate = Math.round(result.successRate);
  const a = result.assumptions ?? {};
  return (
    <Pressable
      onPress={onOpen}
      style={({ pressed }) => [styles.widget, pressed && { opacity: 0.92 }]}
    >
      <View style={styles.wHeader}>
        <View style={styles.wIcon}>
          <Ionicons name="analytics-outline" size={15} color={colors.allworthAccent} />
        </View>
        <Text style={styles.wLabel}>Retirement projection</Text>
        <Ionicons name="expand-outline" size={15} color={colors.inkTertiary} />
      </View>
      <Text style={[styles.bigStat, { color: successColor(rate, false) }]}>{rate}% on track</Text>
      <FanChart snapshots={result.pathSnapshots} height={72} onDark={false} />
      <Text style={styles.wCaption}>
        {result.simulations ?? 500} simulations{a.endAge ? ` · to age ${a.endAge}` : ""}
      </Text>
    </Pressable>
  );
}

function ProjectionDetail({
  result,
  visible,
  onClose,
}: {
  result: any;
  visible: boolean;
  onClose: () => void;
}) {
  const rate = Math.round(result.successRate);
  const a = result.assumptions ?? {};
  const facts: [string, string][] = [
    ["Starting portfolio", a.startingPortfolio != null ? usd(a.startingPortfolio) : "—"],
    ["Annual draw", a.annualDraw != null ? usd(a.annualDraw) : "—"],
    ["Annual spending", a.annualSpending != null ? usd(a.annualSpending) : "—"],
    [
      "Equity allocation",
      a.equityAllocation != null ? `${Math.round(a.equityAllocation * 100)}%` : "—",
    ],
  ];
  return (
    <DetailModal visible={visible} onClose={onClose} title="Retirement projection">
      <View style={{ gap: 6 }}>
        <Text style={[styles.heroStat, { color: successColor(rate, true) }]}>{rate}%</Text>
        <Text style={styles.heroSub}>
          chance your money lasts{a.endAge ? ` to age ${a.endAge}` : ""}, across{" "}
          {result.simulations ?? 500} simulated markets
        </Text>
      </View>
      <View style={styles.chartCard}>
        <FanChart snapshots={result.pathSnapshots} height={200} onDark />
        <View style={styles.legendRow}>
          <Legend swatch="rgba(255,255,255,0.26)" label="Likely range (25–75%)" />
          <Legend swatch="rgba(255,255,255,0.14)" label="Full range (5–95%)" />
        </View>
      </View>
      {result.interpretation ? <Text style={styles.interp}>{result.interpretation}</Text> : null}
      <View style={styles.factGrid}>
        {facts.map(([k, v]) => (
          <View key={k} style={styles.factCell}>
            <Text style={styles.factVal}>{v}</Text>
            <Text style={styles.factKey}>{k}</Text>
          </View>
        ))}
      </View>
      <DanaCta />
    </DetailModal>
  );
}

function Legend({ swatch, label }: { swatch: string; label: string }) {
  return (
    <View style={styles.legend}>
      <View style={[styles.legendSwatch, { backgroundColor: swatch }]} />
      <Text style={styles.legendText}>{label}</Text>
    </View>
  );
}

// ─── Rebalancer ─────────────────────────────────────────────────────────────
function AllocationBar({ alloc }: { alloc: Record<string, number> }) {
  const entries = Object.entries(alloc)
    .filter(([, w]) => w > 0.001)
    .sort((a, b) => b[1] - a[1]);
  return (
    <View>
      <View style={styles.allocBar}>
        {entries.map(([ticker, w], i) => (
          <View
            key={ticker}
            style={{ flex: w, backgroundColor: SLICE_COLORS[i % SLICE_COLORS.length] }}
          />
        ))}
      </View>
      <View style={styles.allocLegend}>
        {entries.slice(0, 4).map(([ticker, w], i) => (
          <View key={ticker} style={styles.allocLegendItem}>
            <View
              style={[styles.allocDot, { backgroundColor: SLICE_COLORS[i % SLICE_COLORS.length] }]}
            />
            <Text style={styles.allocLegendText}>
              {ticker} {Math.round(w * 100)}%
            </Text>
          </View>
        ))}
      </View>
    </View>
  );
}

function RebalanceCard({ result, onOpen }: { result: any; onOpen: () => void }) {
  const trades = result.trades ?? [];
  const tax = result.estimated_tax?.total ?? 0;
  return (
    <Pressable
      onPress={onOpen}
      style={({ pressed }) => [styles.widget, pressed && { opacity: 0.92 }]}
    >
      <View style={styles.wHeader}>
        <View style={styles.wIcon}>
          <Ionicons name="swap-horizontal-outline" size={15} color={colors.allworthAccent} />
        </View>
        <Text style={styles.wLabel}>Rebalance plan</Text>
        <Ionicons name="expand-outline" size={15} color={colors.inkTertiary} />
      </View>
      <Text style={styles.bigStat}>
        {trades.length} {trades.length === 1 ? "trade" : "trades"}
      </Text>
      <AllocationBar alloc={result.target_allocation} />
      <Text style={styles.wCaption}>To your target mix · ≈ {usd(tax)} est. tax</Text>
    </Pressable>
  );
}

function RebalanceDetail({
  result,
  visible,
  onClose,
}: {
  result: any;
  visible: boolean;
  onClose: () => void;
}) {
  const trades = (result.trades ?? []).filter((t: any) => Math.abs(t.amount) > 1);
  const tax = result.estimated_tax ?? {};
  return (
    <DetailModal visible={visible} onClose={onClose} title="Rebalance plan">
      <View style={{ gap: 6 }}>
        <Text style={styles.heroStat}>{trades.length}</Text>
        <Text style={styles.heroSub}>
          tax-aware trades to reach your Core-Satellite 60/40 target
        </Text>
      </View>
      <View style={styles.chartCard}>
        <Text style={styles.cardTitle}>Target allocation</Text>
        <View style={{ marginTop: 12 }}>
          <AllocationBarDark alloc={result.target_allocation} />
        </View>
      </View>
      <View style={{ gap: 2 }}>
        <Text style={styles.cardTitle}>Trades</Text>
        {trades.map((t: any, i: number) => (
          <View key={i} style={[styles.tradeRow, i > 0 && styles.tradeDivider]}>
            <View
              style={[
                styles.tradeTag,
                { backgroundColor: t.action === "SELL" ? colors.lossOnDark : colors.gainOnDark },
              ]}
            >
              <Text style={styles.tradeTagText}>{t.action}</Text>
            </View>
            <Text style={styles.tradeTicker}>{t.ticker}</Text>
            <Text style={styles.tradeAmount}>{usd(t.amount)}</Text>
          </View>
        ))}
      </View>
      <View style={styles.factGrid}>
        <View style={styles.factCell}>
          <Text style={styles.factVal}>{usd(tax.total ?? 0)}</Text>
          <Text style={styles.factKey}>Est. tax cost</Text>
        </View>
        <View style={styles.factCell}>
          <Text style={styles.factVal}>{usd(result.total_portfolio_value ?? 0)}</Text>
          <Text style={styles.factKey}>Portfolio value</Text>
        </View>
      </View>
      <DanaCta />
    </DetailModal>
  );
}

function AllocationBarDark({ alloc }: { alloc: Record<string, number> }) {
  const entries = Object.entries(alloc)
    .filter(([, w]) => w > 0.001)
    .sort((a, b) => b[1] - a[1]);
  return (
    <View style={{ gap: 12 }}>
      <View style={styles.allocBar}>
        {entries.map(([ticker, w], i) => (
          <View
            key={ticker}
            style={{ flex: w, backgroundColor: SLICE_COLORS[i % SLICE_COLORS.length] }}
          />
        ))}
      </View>
      <View style={{ gap: 8 }}>
        {entries.map(([ticker, w], i) => (
          <View key={ticker} style={styles.allocRowDark}>
            <View
              style={[styles.allocDot, { backgroundColor: SLICE_COLORS[i % SLICE_COLORS.length] }]}
            />
            <Text style={styles.allocTickerDark}>{ticker}</Text>
            <Text style={styles.allocPctDark}>{Math.round(w * 100)}%</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

// ─── Dispatcher (what Chat.tsx renders per tool result) ─────────────────────
export function ChatToolWidget({ widget }: { widget: ToolWidget }) {
  const [open, setOpen] = useState(false);
  const r = widget.result;
  if (isProjection(r)) {
    return (
      <FadeScaleIn>
        <ProjectionCard result={r} onOpen={() => setOpen(true)} />
        <ProjectionDetail result={r} visible={open} onClose={() => setOpen(false)} />
      </FadeScaleIn>
    );
  }
  if (isRebalance(r)) {
    return (
      <FadeScaleIn>
        <RebalanceCard result={r} onOpen={() => setOpen(true)} />
        <RebalanceDetail result={r} visible={open} onClose={() => setOpen(false)} />
      </FadeScaleIn>
    );
  }
  return null;
}

const styles = StyleSheet.create({
  // Inline widget card (in the chat stream, light surface)
  widget: { ...card, padding: 14, gap: 10 },
  wHeader: { flexDirection: "row", alignItems: "center", gap: 8 },
  wIcon: {
    width: 26,
    height: 26,
    borderRadius: 8,
    backgroundColor: "rgba(62,113,183,0.12)",
    alignItems: "center",
    justifyContent: "center",
  },
  wLabel: { flex: 1, fontSize: 13, fontFamily: fonts.sansBold, color: colors.inkSecondary },
  bigStat: {
    fontSize: 26,
    fontFamily: fonts.displayMedium,
    color: colors.allworthNavy,
    fontVariant: ["tabular-nums"],
  },
  wCaption: { fontSize: 12.5, fontFamily: fonts.sans, color: colors.inkTertiary },

  // Inline allocation bar
  allocBar: { flexDirection: "row", height: 10, borderRadius: 5, overflow: "hidden" },
  allocLegend: { flexDirection: "row", flexWrap: "wrap", gap: 12, marginTop: 8 },
  allocLegendItem: { flexDirection: "row", alignItems: "center", gap: 5 },
  allocDot: { width: 7, height: 7, borderRadius: 3.5 },
  allocLegendText: {
    fontSize: 12,
    fontFamily: fonts.sans,
    color: colors.inkSecondary,
    fontVariant: ["tabular-nums"],
  },

  // Full-screen modal
  modal: { flex: 1, backgroundColor: colors.chartNightBlue },
  modalTop: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 20,
    paddingBottom: 6,
  },
  modalTitle: { fontSize: 16, fontFamily: fonts.sansBold, color: "#FFFFFF" },
  heroStat: {
    fontSize: 56,
    fontFamily: fonts.displayMedium,
    color: "#FFFFFF",
    fontVariant: ["tabular-nums"],
  },
  heroSub: {
    fontSize: 16,
    fontFamily: fonts.sans,
    color: "rgba(255,255,255,0.78)",
    lineHeight: 22,
  },

  chartCard: {
    backgroundColor: "rgba(255,255,255,0.06)",
    borderRadius: 16,
    padding: 16,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.1)",
  },
  cardTitle: {
    fontSize: 12,
    fontFamily: fonts.sansBold,
    color: "rgba(255,255,255,0.6)",
    textTransform: "uppercase",
    letterSpacing: 0.8,
  },
  legendRow: { flexDirection: "row", gap: 16, marginTop: 12 },
  legend: { flexDirection: "row", alignItems: "center", gap: 6 },
  legendSwatch: { width: 12, height: 12, borderRadius: 3 },
  legendText: { fontSize: 12, fontFamily: fonts.sans, color: "rgba(255,255,255,0.7)" },
  interp: { fontSize: 16, fontFamily: fonts.sans, color: "#FFFFFF", lineHeight: 24 },

  factGrid: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  factCell: {
    flexGrow: 1,
    flexBasis: "44%",
    backgroundColor: "rgba(255,255,255,0.06)",
    borderRadius: 12,
    padding: 14,
    gap: 2,
  },
  factVal: {
    fontSize: 19,
    fontFamily: fonts.displayMedium,
    color: "#FFFFFF",
    fontVariant: ["tabular-nums"],
  },
  factKey: { fontSize: 12.5, fontFamily: fonts.sans, color: "rgba(255,255,255,0.6)" },

  // Trades (dark)
  tradeRow: { flexDirection: "row", alignItems: "center", gap: 12, paddingVertical: 11 },
  tradeDivider: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: "rgba(255,255,255,0.12)",
  },
  tradeTag: { width: 46, paddingVertical: 3, borderRadius: 6, alignItems: "center" },
  tradeTagText: { fontSize: 11, fontFamily: fonts.sansBold, color: colors.allworthNavy },
  tradeTicker: { flex: 1, fontSize: 16, fontFamily: fonts.sansBold, color: "#FFFFFF" },
  tradeAmount: {
    fontSize: 15,
    fontFamily: fonts.sans,
    color: "rgba(255,255,255,0.85)",
    fontVariant: ["tabular-nums"],
  },
  allocRowDark: { flexDirection: "row", alignItems: "center", gap: 10 },
  allocTickerDark: { flex: 1, fontSize: 15, fontFamily: fonts.sansBold, color: "#FFFFFF" },
  allocPctDark: {
    fontSize: 15,
    fontFamily: fonts.sansBold,
    color: "rgba(255,255,255,0.85)",
    fontVariant: ["tabular-nums"],
  },

  cta: {
    flexDirection: "row",
    gap: 8,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#FFFFFF",
    borderRadius: 12,
    paddingVertical: 15,
  },
  ctaSent: { backgroundColor: "rgba(255,255,255,0.12)" },
  ctaText: { fontSize: 16, fontFamily: fonts.sansBold, color: colors.allworthNavy },
});
