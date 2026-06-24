import { Ionicons } from "@expo/vector-icons";
import React, { useEffect, useState } from "react";
import {
  Animated,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { RiseIn, useAnimatedValue } from "../anim";
import { GlassHeader, TAB_BAR_HEIGHT } from "../components/Glass";
import { NetWorthHero } from "../components/NetWorthHero";
import { NudgeCard } from "../components/NudgeCard";
import { DisclaimerFooter, SectionHeader } from "../components/Rows";
import { performanceDeltaLabel } from "../performance";
import { useApp } from "../state";
import { card, colors, fonts, radius, space, text, usd } from "../theme";
import type { Dashboard, Nudge } from "../types";
import { NudgeDetailSheet } from "./NudgeDetailSheet";

export function DashboardScreen() {
  const app = useApp();
  const insets = useSafeAreaInsets();
  const [refreshing, setRefreshing] = useState(false);
  const [selectedNudge, setSelectedNudge] = useState<Nudge | null>(null);

  useEffect(() => {
    if (!app.dashboard) app.loadDashboard();
    if (app.demoScreen === "nudge" && app.dashboard) {
      setSelectedNudge(app.dashboard.nudges[0] ?? null);
      app.clearDemoScreen();
    }
  }, [app.dashboard, app.demoScreen]);

  const refresh = async () => {
    setRefreshing(true);
    await app.loadDashboard();
    setRefreshing(false);
  };

  const d = app.dashboard;
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
        {d ? (
          <DashboardContent d={d} onNudge={setSelectedNudge} />
        ) : app.dashboardError ? (
          <ErrorState message={app.dashboardError} onRetry={app.loadDashboard} />
        ) : (
          <Skeleton />
        )}
      </Animated.ScrollView>
      <GlassHeader title="Home" scrollY={scrollY} />
      <NudgeDetailSheet nudge={selectedNudge} onClose={() => setSelectedNudge(null)} />
    </>
  );
}

function greetingForNow() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

function DashboardContent({ d, onNudge }: { d: Dashboard; onNudge: (n: Nudge) => void }) {
  const app = useApp();
  const insets = useSafeAreaInsets();
  const { width: winW } = useWindowDimensions();
  const nudgeW = Math.min(360, winW - 64); // fixed-width slides so the next card peeks
  const fullName = d.client?.name ?? "Maya Tran";
  const accountCount = d.accounts.allworth.length + d.accounts.outside.length;
  return (
    <View style={{ gap: space[6] }}>
      <NetWorthHero
        greeting={greetingForNow()}
        name={fullName}
        netWorth={d.netWorth}
        delta={trajectory(d)}
        history={d.netWorthHistory}
        insetsTop={insets.top}
        onOpenWealth={() => app.setSelectedTab("invest")}
      />

      {d.nudges.length ? (
        <RiseIn delay={80} style={{ gap: space[3] }}>
          <SectionHeader>Needs your attention</SectionHeader>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            style={styles.carousel}
            contentContainerStyle={styles.carouselContent}
            snapToInterval={nudgeW + space[3]}
            snapToAlignment="start"
            decelerationRate="fast"
          >
            {d.nudges.map((nudge) => (
              <View key={nudge.id} style={{ width: nudgeW }}>
                <NudgeCard nudge={nudge} onPress={() => onNudge(nudge)} fill />
              </View>
            ))}
          </ScrollView>
        </RiseIn>
      ) : null}

      <RiseIn delay={220}>
        <AccountsSummaryLine count={accountCount} onPress={() => app.setSelectedTab("invest")} />
      </RiseIn>

      <View style={{ paddingVertical: space[2] }}>
        <DisclaimerFooter status={d.dataStatus} />
      </View>
    </View>
  );
}

// A single tappable line that hands off to the Wealth tab for the full
// breakdown, instead of duplicating Invest's account/liability card here.
function AccountsSummaryLine({ count, onPress }: { count: number; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [styles.summaryLine, pressed && { opacity: 0.7 }]}
    >
      <Ionicons name="pie-chart-outline" size={18} color={colors.allworthAccent} />
      <Text style={styles.summaryText}>
        Accounts · {count} · View in Wealth
      </Text>
      <Ionicons name="chevron-forward" size={16} color={colors.inkTertiary} />
    </Pressable>
  );
}

// Lead with the long-horizon trajectory, not a one-month dip. A client shouldn't
// log in to "you're down $7k this month" — over the year they're up, which is the
// frame a good advisor uses. The sparkline still shows the recent shape honestly.
function trajectory(d: Dashboard): { text: string; positive: boolean } | undefined {
  const h = d.netWorthHistory;
  if (h.length < 2) return undefined;
  const backendPerf = d.performance?.netWorth;
  if (backendPerf) {
    const sign = backendPerf.gain_loss >= 0 ? "+" : "−";
    return {
      text: `${sign}${usd(Math.abs(backendPerf.gain_loss))} (${sign}${Math.abs(backendPerf.return_pct).toFixed(1)}%) past year`,
      positive: backendPerf.gain_loss >= 0,
    };
  }
  return {
    ...performanceDeltaLabel(h, "past year", d.performanceCashFlows ?? [])!,
  };
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
  // Horizontal carousels bleed past the scroll container's 20px padding to the
  // screen edges, while their content keeps a 20px inset so cards start aligned.
  carousel: { marginHorizontal: -space[5] },
  carouselContent: { paddingHorizontal: space[5], gap: space[3], alignItems: "stretch" },
  summaryLine: {
    ...card,
    flexDirection: "row",
    alignItems: "center",
    gap: space[3],
    paddingHorizontal: space[4],
    paddingVertical: space[4],
    borderRadius: radius.card,
  },
  summaryText: { ...text.body, flex: 1, fontFamily: fonts.sansBold },
  skeletonBlock: { height: 72, borderRadius: radius.card, backgroundColor: colors.inkFaint },
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
