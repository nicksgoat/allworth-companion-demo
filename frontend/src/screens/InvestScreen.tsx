import React, { useEffect, useMemo, useState } from "react";
import { Animated, Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { RiseIn, useAnimatedValue } from "../anim";
import { AdvisorHandoffCard } from "../components/AdvisorHandoffCard";
import { GlassHeader, TAB_BAR_HEIGHT } from "../components/Glass";
import { AllocationCard } from "../components/AllocationCard";
import { HeroNumber } from "../components/HeroNumber";
import { AccountHoldingsSection } from "../components/Holdings";
import { IncomeCard } from "../components/IncomeCard";
import { BreakdownCard, CompletePictureCard } from "../components/NetWorthBreakdown";
import { NetWorthDetail } from "../components/NetWorthDetail";
import { NudgeCard } from "../components/NudgeCard";
import { RangeChips } from "../components/RangeChips";
import { RecurringCard } from "../components/RecurringCard";
import { DisclaimerFooter, SectionHeader } from "../components/Rows";
import { SegmentedControl } from "../components/SegmentedControl";
import { Sparkline } from "../components/Sparkline";
import { AllworthWordmark } from "../components/Wordmark";
import { performanceDeltaLabel } from "../performance";
import { useApp } from "../state";
import { colors, fonts } from "../theme";
import type { AssetClass, Dashboard, Nudge, Portfolio, Position } from "../types";
import { ClassDetailSheet } from "./ClassDetailSheet";
import { NudgeDetailSheet } from "./NudgeDetailSheet";
import { PositionDetailSheet } from "./PositionDetailSheet";

const RANGES: { label: string; points: number; deltaSuffix: string }[] = [
  { label: "3M", points: 4, deltaSuffix: "past 3 months" },
  { label: "6M", points: 7, deltaSuffix: "past 6 months" },
  { label: "1Y", points: 12, deltaSuffix: "past year" },
];

export function InvestScreen() {
  const app = useApp();
  const insets = useSafeAreaInsets();
  const [refreshing, setRefreshing] = useState(false);
  const [selectedNudge, setSelectedNudge] = useState<Nudge | null>(null);
  const [selectedPosition, setSelectedPosition] = useState<Position | null>(null);
  const [selectedClass, setSelectedClass] = useState<AssetClass | null>(null);

  useEffect(() => {
    if (!app.dashboard) app.loadDashboard();
    if (!app.portfolio) app.loadPortfolio();
  }, [app.dashboard, app.portfolio]);

  const refresh = async () => {
    setRefreshing(true);
    await Promise.all([app.loadDashboard(), app.loadPortfolio()]);
    setRefreshing(false);
  };

  const retry = () => {
    app.loadDashboard();
    app.loadPortfolio();
  };

  const d = app.dashboard;
  const p = app.portfolio;
  const error = app.dashboardError ?? app.portfolioError;

  const scrollY = useAnimatedValue(0);

  return (
    <>
      <Animated.ScrollView
        style={{ backgroundColor: colors.surfacePrimary }}
        directionalLockEnabled
        contentContainerStyle={{
          padding: 20,
          paddingTop: insets.top + 8,
          paddingBottom: TAB_BAR_HEIGHT + insets.bottom + 24,
        }}
        onScroll={Animated.event([{ nativeEvent: { contentOffset: { y: scrollY } } }], {
          useNativeDriver: false,
        })}
        scrollEventThrottle={16}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
      >
        {d && p ? (
          <InvestContent
            d={d}
            p={p}
            onNudge={setSelectedNudge}
            onPosition={setSelectedPosition}
            onClass={setSelectedClass}
          />
        ) : error ? (
          <ErrorState message={error} onRetry={retry} />
        ) : (
          <Skeleton />
        )}
      </Animated.ScrollView>
      <GlassHeader title="Your wealth" scrollY={scrollY} />
      <NudgeDetailSheet nudge={selectedNudge} onClose={() => setSelectedNudge(null)} />
      <PositionDetailSheet
        position={selectedPosition}
        account={
          selectedPosition && d
            ? ([...d.accounts.allworth, ...d.accounts.outside].find(
                (a) => a.id === selectedPosition.accountId,
              ) ?? null)
            : null
        }
        onClose={() => setSelectedPosition(null)}
      />
      <ClassDetailSheet
        assetClass={selectedClass}
        positions={p?.positions ?? []}
        accounts={d ? [...d.accounts.allworth, ...d.accounts.outside] : []}
        onClose={() => setSelectedClass(null)}
      />
    </>
  );
}

function InvestContent({
  d,
  p,
  onNudge,
  onPosition,
  onClass,
}: {
  d: Dashboard;
  p: Portfolio;
  onNudge: (n: Nudge) => void;
  onPosition: (pos: Position) => void;
  onClass: (c: AssetClass) => void;
}) {
  const app = useApp();
  const [range, setRange] = useState("1Y");
  const [segment, setSegment] = useState("Overview");
  const [chartOpen, setChartOpen] = useState(false);

  const ask = (prompt: string) => {
    app.setChatPrefill(prompt);
    app.setSelectedTab("chat");
  };

  const { slice, delta } = useMemo(() => {
    const history = d.netWorthHistory;
    const spec = RANGES.find((r) => r.label === range) ?? RANGES[RANGES.length - 1];
    const sliced = history.length >= spec.points ? history.slice(-spec.points) : history;
    if (sliced.length < 2) return { slice: sliced, delta: undefined };
    const perf = performanceDeltaLabel(sliced, spec.deltaSuffix, d.performanceCashFlows ?? []);
    return {
      slice: sliced,
      delta: perf ? { text: perf.text, positive: perf.positive } : undefined,
    };
  }, [d.netWorthHistory, d.performanceCashFlows, range]);

  const askRebalance = () => {
    app.setChatPrefill(
      "How does my current mix compare to my 60/40 plan, and what would rebalancing look like?",
    );
    app.setSelectedTab("chat");
  };

  const accounts = [...d.accounts.allworth, ...d.accounts.outside];
  const investedAccounts = accounts.filter((a) => p.byAccount[a.id]?.length);
  const concentrationNudges = d.nudges.filter((n) => n.type === "concentration");

  return (
    <View style={{ gap: 24 }}>
      <View style={styles.headerRow}>
        <Text style={styles.title} numberOfLines={1} adjustsFontSizeToFit>
          Your wealth
        </Text>
        <AllworthWordmark />
      </View>

      <RiseIn style={{ gap: 14 }}>
        <Pressable
          onPress={() => setChartOpen(true)}
          style={({ pressed }) => pressed && { opacity: 0.7 }}
        >
          <HeroNumber label="Total net worth" value={d.netWorth} delta={delta} />
        </Pressable>
        <RangeChips options={RANGES.map((r) => r.label)} selected={range} onSelect={setRange} />
        <Sparkline points={slice} />
      </RiseIn>

      <NetWorthDetail visible={chartOpen} onClose={() => setChartOpen(false)} d={d} />

      <RiseIn delay={60}>
        <SegmentedControl
          options={["Overview", "Holdings"]}
          selected={segment}
          onSelect={setSegment}
        />
      </RiseIn>

      {segment === "Overview" ? (
        <View key="overview" style={{ gap: 24 }}>
          <RiseIn>
            <BreakdownCard
              allworthTotal={d.allworthTotal}
              heldAwayTotal={d.heldAwayTotal}
              liabilitiesTotal={d.liabilitiesTotal}
            />
          </RiseIn>

          <RiseIn delay={60}>
            <CompletePictureCard heldAwayTotal={d.heldAwayTotal} />
          </RiseIn>

          <RiseIn delay={120} style={{ gap: 12 }}>
            <SectionHeader>Your allocation</SectionHeader>
            <AllocationCard
              positions={p.positions}
              onAskRebalance={askRebalance}
              onSelectClass={onClass}
            />
            <AdvisorHandoffCard />
          </RiseIn>

          {concentrationNudges.map((nudge, i) => (
            <RiseIn key={nudge.id} delay={180 + i * 60}>
              <NudgeCard nudge={nudge} onPress={() => onNudge(nudge)} />
            </RiseIn>
          ))}

          <RiseIn delay={240} style={{ gap: 12 }}>
            <SectionHeader>Automatic investing</SectionHeader>
            <RecurringCard
              onAsk={() => ask("Could I be investing more each month without hurting my plan?")}
            />
          </RiseIn>
        </View>
      ) : (
        <View key="holdings" style={{ gap: 24 }}>
          <RiseIn style={{ gap: 16 }}>
            {investedAccounts.map((account) => (
              <AccountHoldingsSection
                key={account.id}
                account={account}
                positions={p.byAccount[account.id]}
                onSelect={onPosition}
              />
            ))}
          </RiseIn>

          <RiseIn delay={60} style={{ gap: 12 }}>
            <SectionHeader>Income</SectionHeader>
            <IncomeCard
              positions={p.positions}
              accounts={accounts}
              onAsk={() => ask("What income could my portfolio generate in retirement?")}
            />
          </RiseIn>
        </View>
      )}

      <View style={{ paddingVertical: 8 }}>
        <DisclaimerFooter />
      </View>
    </View>
  );
}

function Skeleton() {
  return (
    <View style={{ gap: 20 }}>
      {[0, 1, 2, 3, 4].map((i) => (
        <View key={i} style={styles.skeletonBlock} />
      ))}
    </View>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <View style={styles.errorBox}>
      <Text style={styles.errorTitle}>We couldn{"'"}t load your accounts</Text>
      <Text style={styles.errorMessage}>{message}</Text>
      <Pressable onPress={onRetry} style={styles.retryButton}>
        <Text style={styles.retryText}>Retry</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  title: { fontSize: 28, fontFamily: fonts.display, color: colors.inkPrimary, flexShrink: 1 },
  skeletonBlock: { height: 72, borderRadius: 12, backgroundColor: colors.inkFaint },
  errorBox: { alignItems: "center", paddingTop: 120, gap: 10, paddingHorizontal: 20 },
  errorTitle: { fontSize: 20, fontFamily: fonts.displayMedium, color: colors.inkPrimary },
  errorMessage: {
    fontSize: 15,
    fontFamily: fonts.sans,
    color: colors.inkSecondary,
    textAlign: "center",
  },
  retryButton: {
    marginTop: 6,
    backgroundColor: colors.allworthAccent,
    paddingHorizontal: 18,
    paddingVertical: 10,
    borderRadius: 10,
  },
  retryText: { color: "#fff", fontSize: 15, fontFamily: fonts.sansBold },
});
