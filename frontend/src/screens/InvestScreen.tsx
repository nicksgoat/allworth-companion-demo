import React, { useEffect, useState } from "react";
import { Animated, Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { RiseIn, useAnimatedValue } from "../anim";
import { AdvisorHandoffCard } from "../components/AdvisorHandoffCard";
import { APP_HEADER_HEIGHT, AppHeader, TAB_BAR_HEIGHT } from "../components/Glass";
import { AllocationCard } from "../components/AllocationCard";
import { AccountHoldingsSection } from "../components/Holdings";
import { IncomeCard } from "../components/IncomeCard";
import { BreakdownCard, CompletePictureCard } from "../components/NetWorthBreakdown";
import { NudgeCard } from "../components/NudgeCard";
import { RecurringCard } from "../components/RecurringCard";
import { DisclaimerFooter, SectionHeader } from "../components/Rows";
import { SegmentedControl } from "../components/SegmentedControl";
import { useApp } from "../state";
import { colors, fonts } from "../theme";
import type { AssetClass, Dashboard, Nudge, Portfolio, Position } from "../types";
import { ClassDetailSheet } from "./ClassDetailSheet";
import { NudgeDetailSheet } from "./NudgeDetailSheet";
import { PositionDetailSheet } from "./PositionDetailSheet";

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
          paddingTop: insets.top + APP_HEADER_HEIGHT + 8,
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
      <AppHeader title="Your wealth" scrollY={scrollY} />
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

// Compliance-shaped by design (stakeholder rules): no combined-total headline,
// no performance deltas, no trajectory chart at screen level. The screen leads
// with structure — managed vs held away vs owed — and guides toward the
// advisor and chat. Performance detail lives only inside tapped-in sheets.
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
  const [segment, setSegment] = useState("Overview");

  const ask = (prompt: string) => {
    app.setChatPrefill(prompt);
    app.setSelectedTab("chat");
  };

  const askRebalance = () => {
    ask("How does my current mix compare to my 60/40 plan, and what would rebalancing look like?");
  };

  const accounts = [...d.accounts.allworth, ...d.accounts.outside];
  const investedAccounts = accounts.filter((a) => p.byAccount[a.id]?.length);
  const concentrationNudges = d.nudges.filter((n) => n.type === "concentration");
  const accountCount = accounts.length;

  return (
    <View style={{ gap: 24 }}>
      <RiseIn style={{ gap: 14 }}>
        <View style={{ gap: 6 }}>
          <Text style={styles.leadTitle}>Where your money lives</Text>
          <Text style={styles.leadSubtitle}>
            {accountCount} accounts — managed, held away, and owed.
          </Text>
        </View>
        <BreakdownCard
          allworthTotal={d.allworthTotal}
          heldAwayTotal={d.heldAwayTotal}
          liabilitiesTotal={d.liabilitiesTotal}
        />
      </RiseIn>

      <RiseIn delay={60}>
        <SegmentedControl
          options={["Overview", "Holdings"]}
          selected={segment}
          onSelect={setSegment}
        />
      </RiseIn>

      {segment === "Overview" ? (
        <View key="overview" style={{ gap: 24 }}>
          <RiseIn style={{ gap: 12 }}>
            <SectionHeader>Your allocation</SectionHeader>
            <AllocationCard
              positions={p.positions}
              onAskRebalance={askRebalance}
              onSelectClass={onClass}
            />
            <AdvisorHandoffCard />
          </RiseIn>

          {concentrationNudges.map((nudge, i) => (
            <RiseIn key={nudge.id} delay={60 + i * 60}>
              <NudgeCard nudge={nudge} onPress={() => onNudge(nudge)} />
            </RiseIn>
          ))}

          <RiseIn delay={120}>
            <CompletePictureCard heldAwayTotal={d.heldAwayTotal} />
          </RiseIn>

          <RiseIn delay={180}>
            <RecurringCard
              onAsk={() => ask("Could I be investing more each month without hurting my plan?")}
            />
          </RiseIn>
        </View>
      ) : (
        <View key="holdings" style={{ gap: 24 }}>
          <RiseIn style={{ gap: 16 }}>
            {investedAccounts.map((account, i) => (
              <AccountHoldingsSection
                key={account.id}
                account={account}
                positions={p.byAccount[account.id]}
                onSelect={onPosition}
                initiallyExpanded={i === 0}
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
  leadTitle: { fontSize: 28, fontFamily: fonts.displayMedium, color: colors.allworthNavy },
  leadSubtitle: {
    fontSize: 15,
    fontFamily: fonts.sans,
    lineHeight: 21,
    color: colors.inkSecondary,
  },
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
