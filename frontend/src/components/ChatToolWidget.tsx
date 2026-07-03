import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import React, { useId, useRef, useState } from "react";
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
import Svg, {
  Circle,
  Defs,
  Line,
  LinearGradient,
  Path,
  Stop,
  Text as SvgText,
} from "react-native-svg";
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

// Catmull-Rom → cubic bezier, matching the smoothing used in the other charts.
type Pt = { x: number; y: number };
function smooth(pts: Pt[]): string {
  if (pts.length < 2) return pts.length ? `M ${pts[0].x.toFixed(1)} ${pts[0].y.toFixed(1)}` : "";
  let d = `M ${pts[0].x.toFixed(1)} ${pts[0].y.toFixed(1)}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[Math.min(pts.length - 1, i + 2)];
    const c1x = p1.x + (p2.x - p0.x) / 6;
    const c1y = p1.y + (p2.y - p0.y) / 6;
    const c2x = p2.x - (p3.x - p1.x) / 6;
    const c2y = p2.y - (p3.y - p1.y) / 6;
    d += ` C ${c1x.toFixed(1)} ${c1y.toFixed(1)}, ${c2x.toFixed(1)} ${c2y.toFixed(1)}, ${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`;
  }
  return d;
}

// ─── Monte-Carlo fan chart ──────────────────────────────────────────────────
// Full fidelity (smooth gradient bands, $ + age axes, $0 baseline, end dot).
// `interactive` adds drag-to-scrub; when false the chart doesn't capture touches,
// so a tap bubbles up to the card's Pressable and opens the full-screen detail.
function FanChart({
  snapshots,
  height,
  onDark,
  interactive,
}: {
  snapshots: any[];
  height: number;
  onDark: boolean;
  interactive?: boolean;
}) {
  const [w, setW] = useState(0);
  const [sel, setSel] = useState<number | null>(null);
  const startRef = useRef({ x: 0, y: 0 });
  const uid = useId().replace(/:/g, "");
  if (!snapshots || snapshots.length < 2) return null;

  const padL = 44;
  const padR = 12;
  const padT = 8;
  const padB = 22;
  const pw = w - padL - padR;
  const ph = height - padT - padB;
  // Scale to the likely-range upper bound (p75) so the median + middle band fill
  // the chart, instead of being crushed by the lucky p95 path. p95 clamps at top.
  const yMax = Math.max(...snapshots.map((s) => s.p75)) * 1.4 || 1;
  const x = (i: number) => padL + (i / (snapshots.length - 1)) * pw;
  const y = (v: number) => Math.max(padT, Math.min(padT + ph, padT + ph - (v / yMax) * ph));
  const pts = (k: string): Pt[] => snapshots.map((s, i) => ({ x: x(i), y: y(s[k]) }));
  const band = (upKey: string, lowKey: string): string => {
    const up = pts(upKey);
    const low = pts(lowKey).reverse();
    const tail = smooth(low).replace(/^M[^C]*/, "");
    return `${smooth(up)} L ${low[0].x.toFixed(1)} ${low[0].y.toFixed(1)} ${tail} Z`;
  };
  const grid = [0, yMax / 2, yMax];
  const xIdx = [0, Math.floor((snapshots.length - 1) / 2), snapshots.length - 1];
  const last = snapshots.length - 1;
  const s = sel != null ? snapshots[sel] : null;

  const tone = onDark ? "#9FC3E8" : colors.allworthAccent;
  const lineC = onDark ? "#FFFFFF" : colors.allworthNavy;
  const axisC = onDark ? "rgba(255,255,255,0.5)" : colors.inkTertiary;
  const gridC = onDark ? "#FFFFFF" : colors.inkSecondary;
  const fontSize = interactive ? 10 : 9;

  const select = (locX: number) => {
    if (!pw) return;
    const i = Math.max(0, Math.min(last, Math.round(((locX - padL) / pw) * last)));
    setSel((prev) => {
      if (prev !== i) Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
      return i;
    });
  };
  const responder = interactive
    ? {
        onStartShouldSetResponder: (e: any) => {
          startRef.current = { x: e.nativeEvent.pageX, y: e.nativeEvent.pageY };
          return false;
        },
        onMoveShouldSetResponder: (e: any) =>
          Math.abs(e.nativeEvent.pageX - startRef.current.x) > 8 &&
          Math.abs(e.nativeEvent.pageX - startRef.current.x) >
            Math.abs(e.nativeEvent.pageY - startRef.current.y),
        onResponderGrant: (e: any) => select(e.nativeEvent.locationX),
        onResponderMove: (e: any) => select(e.nativeEvent.locationX),
        onResponderRelease: () => setSel(null),
        onResponderTerminate: () => setSel(null),
      }
    : {};

  return (
    <View
      style={{ height }}
      onLayout={(e: LayoutChangeEvent) => setW(e.nativeEvent.layout.width)}
      {...responder}
    >
      {w > 0 ? (
        <Svg width={w} height={height}>
          <Defs>
            <LinearGradient id={`fanOut${uid}`} x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor={tone} stopOpacity={onDark ? 0.3 : 0.2} />
              <Stop offset="1" stopColor={tone} stopOpacity={onDark ? 0.08 : 0.05} />
            </LinearGradient>
            <LinearGradient id={`fanIn${uid}`} x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor={tone} stopOpacity={onDark ? 0.55 : 0.38} />
              <Stop offset="1" stopColor={tone} stopOpacity={onDark ? 0.24 : 0.16} />
            </LinearGradient>
          </Defs>
          {grid.map((v, i) => (
            <Line
              key={i}
              x1={padL}
              y1={y(v)}
              x2={w - padR}
              y2={y(v)}
              stroke={v === 0 ? lineC : gridC}
              strokeOpacity={v === 0 ? 0.3 : onDark ? 0.08 : 0.12}
              strokeWidth={1}
              strokeDasharray={v === 0 ? "2 5" : undefined}
            />
          ))}
          <Path d={band("p95", "p5")} fill={`url(#fanOut${uid})`} />
          <Path d={band("p75", "p25")} fill={`url(#fanIn${uid})`} />
          <Path
            d={smooth(pts("median"))}
            stroke={lineC}
            strokeOpacity={onDark ? 0.22 : 0.12}
            strokeWidth={6}
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <Path
            d={smooth(pts("median"))}
            stroke={lineC}
            strokeWidth={2.5}
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {s ? (
            <>
              <Line
                x1={x(sel!)}
                y1={padT}
                x2={x(sel!)}
                y2={padT + ph}
                stroke={lineC}
                strokeOpacity={0.4}
                strokeWidth={1}
              />
              <Circle cx={x(sel!)} cy={y(s.median)} r={5} fill={lineC} />
            </>
          ) : (
            <Circle cx={x(last)} cy={y(snapshots[last].median)} r={3.5} fill={lineC} />
          )}
          {grid.map((v, i) => (
            <SvgText
              key={i}
              x={padL - 6}
              y={y(v) + 3.5}
              fontSize={fontSize}
              fill={axisC}
              textAnchor="end"
            >
              {usdCompact(v)}
            </SvgText>
          ))}
          {xIdx.map((idx, i) => (
            <SvgText
              key={i}
              x={x(idx)}
              y={height - 6}
              fontSize={fontSize}
              fill={axisC}
              textAnchor="middle"
            >
              {interactive ? `Age ${snapshots[idx].age}` : snapshots[idx].age}
            </SvgText>
          ))}
        </Svg>
      ) : null}
      {s ? (
        <View
          style={[
            styles.scrubTip,
            { left: Math.min(Math.max(x(sel!) - 72, padL), w - padR - 144) },
          ]}
        >
          <Text style={styles.scrubAge}>Age {s.age}</Text>
          <Text style={styles.scrubMed}>{usdCompact(s.median)} median</Text>
          <Text style={styles.scrubRange}>
            likely {usdCompact(s.p25)}–{usdCompact(s.p75)}
          </Text>
        </View>
      ) : null}
    </View>
  );
}

function usdCompact(n: number): string {
  const a = Math.abs(n);
  if (a >= 1e6) return `$${(n / 1e6).toFixed(a >= 1e7 ? 0 : 1)}M`;
  if (a >= 1e3) return `$${Math.round(n / 1e3)}K`;
  return `$${Math.round(n)}`;
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
      <FanChart snapshots={result.pathSnapshots} height={150} onDark={false} />
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
        <FanChart snapshots={result.pathSnapshots} height={240} onDark interactive />
        <View style={styles.legendRow}>
          <Legend swatch="rgba(159,195,232,0.55)" label="Likely range (25–75%)" />
          <Legend swatch="rgba(159,195,232,0.3)" label="Full range (5–95%)" />
          <Text style={styles.dragHint}>drag to explore</Text>
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
// Derive the pre-rebalance (current) mix from the post-trade mix + the trades —
// the result only carries the post-trade allocation, so we back out the trades.
function deriveCurrent(result: any): Record<string, number> {
  const total = result.total_portfolio_value || 1;
  const post = result.post_trade_allocation ?? {};
  const target = result.target_allocation ?? {};
  const net: Record<string, number> = {};
  for (const t of result.trades ?? []) {
    net[t.ticker] = (net[t.ticker] ?? 0) + (t.action === "BUY" ? t.amount : -t.amount);
  }
  const tickers = new Set([...Object.keys(post), ...Object.keys(target), ...Object.keys(net)]);
  const cur: Record<string, number> = {};
  let sum = 0;
  for (const tk of tickers) {
    const w = Math.max(0, (post[tk] ?? 0) * total - (net[tk] ?? 0)) / total;
    cur[tk] = w;
    sum += w;
  }
  // If the back-out looks off (rounding/missing data), fall back to the target.
  return Math.abs(sum - 1) > 0.3 ? { ...target } : cur;
}

// Stable ticker → colour map, ordered by target weight so both bars line up.
function tickerColors(
  target: Record<string, number>,
  current: Record<string, number>,
): Record<string, string> {
  const all = Array.from(new Set([...Object.keys(target), ...Object.keys(current)]));
  all.sort((a, b) => (target[b] ?? 0) - (target[a] ?? 0) || (current[b] ?? 0) - (current[a] ?? 0));
  const map: Record<string, string> = {};
  all.forEach((tk, i) => (map[tk] = SLICE_COLORS[i % SLICE_COLORS.length]));
  return map;
}

function MixBar({
  alloc,
  colorMap,
}: {
  alloc: Record<string, number>;
  colorMap: Record<string, string>;
}) {
  const entries = Object.entries(alloc)
    .filter(([, w]) => w > 0.002)
    .sort((a, b) => b[1] - a[1]);
  return (
    <View style={styles.mixBar}>
      {entries.map(([tk, w]) => (
        <View
          key={tk}
          style={{ flex: w, backgroundColor: colorMap[tk] ?? colors.chartLightGray }}
        />
      ))}
    </View>
  );
}

// The rebalance "chart": the Now → Target allocation shift, same colours aligned.
function AllocationShift({
  result,
  onDark,
  detailed,
}: {
  result: any;
  onDark: boolean;
  detailed?: boolean;
}) {
  const target = result.target_allocation ?? {};
  const current = deriveCurrent(result);
  const colorMap = tickerColors(target, current);
  const labelC = onDark ? "rgba(255,255,255,0.55)" : colors.inkTertiary;
  const tickerC = onDark ? "#FFFFFF" : colors.inkPrimary;
  const pctC = onDark ? "rgba(255,255,255,0.85)" : colors.inkSecondary;
  const top = Object.entries(target)
    .filter(([, w]) => (w as number) > 0.002)
    .sort((a, b) => (b[1] as number) - (a[1] as number))
    .slice(0, 5);
  return (
    <View style={{ gap: detailed ? 14 : 11 }}>
      <View style={{ gap: 5 }}>
        <Text style={[styles.mixLabel, { color: labelC }]}>Now</Text>
        <MixBar alloc={current} colorMap={colorMap} />
      </View>
      <View style={{ gap: 5 }}>
        <Text style={[styles.mixLabel, { color: labelC }]}>Target</Text>
        <MixBar alloc={target} colorMap={colorMap} />
      </View>
      {detailed ? (
        <View style={{ gap: 10, marginTop: 2 }}>
          {top.map(([tk, w]) => (
            <View key={tk} style={styles.shiftRow}>
              <View style={[styles.allocDot, { backgroundColor: colorMap[tk] }]} />
              <Text style={[styles.shiftTicker, { color: tickerC }]}>{tk}</Text>
              <Text style={[styles.shiftPct, { color: pctC }]}>
                {Math.round((current[tk] ?? 0) * 100)}% → {Math.round((w as number) * 100)}%
              </Text>
            </View>
          ))}
        </View>
      ) : null}
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
      <AllocationShift result={result} onDark={false} />
      <Text style={styles.wCaption}>To your 60/40 target · ≈ {usd(tax)} est. tax</Text>
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
  const tax = result.estimated_tax ?? {};
  const allTrades = (result.trades ?? [])
    .filter((t: any) => Math.abs(t.amount) > 1)
    .sort((a: any, b: any) => Math.abs(b.amount) - Math.abs(a.amount));
  const shown = allTrades.slice(0, 8);
  const more = allTrades.length - shown.length;
  return (
    <DetailModal visible={visible} onClose={onClose} title="Rebalance plan">
      <View style={{ gap: 6 }}>
        <Text style={styles.heroStat}>{allTrades.length}</Text>
        <Text style={styles.heroSub}>
          tax-aware trades to move from your current mix to the Core-Satellite 60/40 target
        </Text>
      </View>
      <View style={styles.chartCard}>
        <Text style={styles.cardTitle}>Allocation: now → target</Text>
        <View style={{ marginTop: 14 }}>
          <AllocationShift result={result} onDark detailed />
        </View>
      </View>
      <View style={{ gap: 2 }}>
        <Text style={styles.cardTitle}>Largest trades</Text>
        {shown.map((t: any, i: number) => (
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
        {more > 0 ? <Text style={styles.tradeMore}>+ {more} smaller trades</Text> : null}
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
    </DetailModal>
  );
}

// ─── Live goal planner (stakeholder ask: adjustable goal + cash-flow card
// that appears when a goal comes up in conversation). Deterministic local
// math — the LLM narrates, the widget lets the client turn the dials. ───────
type GoalPlan = {
  goalLabel: string;
  target: number;
  saved: number;
  years: number;
};

const GOAL_YEARS = [3, 4, 5];
const GOAL_MONTHLY = [2000, 3000, 4500];
const MONTHLY_GROWTH = 0.0035; // ~4.3%/yr, conservative planning rate

function isGoalPlan(r: any): r is GoalPlan {
  return r && typeof r.target === "number" && typeof r.goalLabel === "string";
}

function projectGoal(saved: number, monthly: number, months: number): number {
  let v = saved;
  for (let i = 0; i < months; i++) v = v * (1 + MONTHLY_GROWTH) + monthly;
  return Math.round(v);
}

function GoalPlannerCard({ plan }: { plan: GoalPlan }) {
  const [years, setYears] = useState(plan.years);
  const [monthly, setMonthly] = useState(GOAL_MONTHLY[1]);
  const projected = projectGoal(plan.saved, monthly, years * 12);
  const pct = Math.min(1, projected / plan.target);
  const onTrack = projected >= plan.target;

  const pick = <T,>(setter: (v: T) => void) => (v: T) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setter(v);
  };

  return (
    <View style={styles.widget}>
      <View style={styles.goalHeader}>
        <Ionicons name="flag-outline" size={14} color={colors.allworthAccent} />
        <Text style={styles.goalTitle}>{plan.goalLabel}</Text>
        <Text style={[styles.goalVerdict, { color: onTrack ? colors.gain : colors.attention }]}>
          {onTrack ? "On track" : "Falling short"}
        </Text>
      </View>

      <Text style={styles.goalProjection}>
        {usd(projected)} <Text style={styles.goalOf}>of {usd(plan.target)} by year {years}</Text>
      </Text>
      <View style={styles.goalTrack}>
        <View
          style={[
            styles.goalFill,
            { width: `${Math.round(pct * 100)}%` },
            { backgroundColor: onTrack ? colors.chartEvergreen : colors.chartPumpkin },
          ]}
        />
      </View>

      <View style={styles.goalDialRow}>
        <Text style={styles.goalDialLabel}>Timeline</Text>
        {GOAL_YEARS.map((y) => (
          <Pressable
            key={y}
            onPress={() => pick(setYears)(y)}
            style={[styles.goalChip, years === y && styles.goalChipActive]}
          >
            <Text style={[styles.goalChipText, years === y && styles.goalChipTextActive]}>
              {y} yr
            </Text>
          </Pressable>
        ))}
      </View>
      <View style={styles.goalDialRow}>
        <Text style={styles.goalDialLabel}>Monthly</Text>
        {GOAL_MONTHLY.map((m) => (
          <Pressable
            key={m}
            onPress={() => pick(setMonthly)(m)}
            style={[styles.goalChip, monthly === m && styles.goalChipActive]}
          >
            <Text style={[styles.goalChipText, monthly === m && styles.goalChipTextActive]}>
              ${(m / 1000).toFixed(m % 1000 ? 1 : 0)}k
            </Text>
          </Pressable>
        ))}
      </View>

      <Text style={styles.goalFootnote}>
        Assumes a conservative planning rate. Adjust the dials, then pressure-test the plan with
        your advisor.
      </Text>
    </View>
  );
}

// ─── Dispatcher (what Chat.tsx renders per tool result) ─────────────────────
export function ChatToolWidget({ widget }: { widget: ToolWidget }) {
  const [open, setOpen] = useState(false);
  const r = widget.result;
  if (widget.name === "goal_planner" && isGoalPlan(r)) {
    return (
      <FadeScaleIn>
        <GoalPlannerCard plan={r} />
      </FadeScaleIn>
    );
  }
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
  // Live goal planner
  goalHeader: { flexDirection: "row", alignItems: "center", gap: 6 },
  goalTitle: { flex: 1, fontSize: 13, fontFamily: fonts.sansBold, color: colors.inkSecondary },
  goalVerdict: { fontSize: 12, fontFamily: fonts.sansBold },
  goalProjection: { fontSize: 22, fontFamily: fonts.displayMedium, color: colors.inkPrimary },
  goalOf: { fontSize: 13, fontFamily: fonts.sans, color: colors.inkTertiary },
  goalTrack: { height: 6, borderRadius: 3, backgroundColor: colors.inkFaint, overflow: "hidden" },
  goalFill: { height: 6, borderRadius: 3 },
  goalDialRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  goalDialLabel: { width: 62, fontSize: 12, fontFamily: fonts.sans, color: colors.inkTertiary },
  goalChip: {
    borderWidth: 1,
    borderColor: colors.hairline,
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 5,
  },
  goalChipActive: { borderColor: colors.allworthNavy, backgroundColor: colors.allworthNavy },
  goalChipText: { fontSize: 12, fontFamily: fonts.sansBold, color: colors.inkSecondary },
  goalChipTextActive: { color: "#FFFFFF" },
  goalFootnote: { fontSize: 11, fontFamily: fonts.sans, color: colors.inkTertiary, lineHeight: 15 },
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

  // Allocation shift (Now → Target)
  mixBar: { flexDirection: "row", height: 14, borderRadius: 7, overflow: "hidden" },
  mixLabel: {
    fontSize: 11,
    fontFamily: fonts.sansBold,
    letterSpacing: 0.6,
    textTransform: "uppercase",
  },
  allocDot: { width: 9, height: 9, borderRadius: 4.5 },
  shiftRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  shiftTicker: { flex: 1, fontSize: 15, fontFamily: fonts.sansBold },
  shiftPct: { fontSize: 14, fontFamily: fonts.sans, fontVariant: ["tabular-nums"] },

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
  dragHint: {
    marginLeft: "auto",
    fontSize: 11,
    fontFamily: fonts.sansItalic,
    color: "rgba(255,255,255,0.4)",
  },
  scrubTip: {
    position: "absolute",
    top: 4,
    width: 144,
    backgroundColor: "rgba(7,28,48,0.94)",
    borderRadius: 10,
    paddingVertical: 8,
    paddingHorizontal: 10,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.16)",
  },
  scrubAge: { fontSize: 11, fontFamily: fonts.sansBold, color: "rgba(255,255,255,0.6)" },
  scrubMed: {
    fontSize: 16,
    fontFamily: fonts.sansBold,
    color: "#FFFFFF",
    fontVariant: ["tabular-nums"],
    marginTop: 1,
  },
  scrubRange: {
    fontSize: 11.5,
    fontFamily: fonts.sans,
    color: "rgba(255,255,255,0.65)",
    marginTop: 1,
    fontVariant: ["tabular-nums"],
  },
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
  tradeMore: {
    fontSize: 13,
    fontFamily: fonts.sans,
    color: "rgba(255,255,255,0.5)",
    paddingTop: 10,
  },
});
