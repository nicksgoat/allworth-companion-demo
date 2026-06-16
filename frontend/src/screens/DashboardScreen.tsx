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
import { DisclaimerFooter, HairlineDivider, SectionHeader } from "../components/Rows";
import { useApp } from "../state";
import { card, colors, fonts, usd } from "../theme";
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
  return (
    <View style={{ gap: 24 }}>
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
        <RiseIn delay={80} style={{ gap: 12 }}>
          <SectionHeader>Needs your attention</SectionHeader>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            style={styles.carousel}
            contentContainerStyle={styles.carouselContent}
            snapToInterval={nudgeW + 12}
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

      <RiseIn delay={220} style={{ gap: 12 }}>
        <SectionHeader>Quick actions</SectionHeader>
        <QuickActions />
      </RiseIn>

      <RiseIn delay={280} style={{ gap: 12 }}>
        <SectionHeader>Your accounts</SectionHeader>
        <AccountsSnapshotCard d={d} />
      </RiseIn>

      <View style={{ paddingVertical: 8 }}>
        <DisclaimerFooter />
      </View>
    </View>
  );
}

function QuickActions() {
  const app = useApp();

  const actions: { icon: keyof typeof Ionicons.glyphMap; label: string; onPress: () => void }[] = [
    {
      icon: "chatbubbles-outline",
      label: "Ask anything",
      onPress: () => app.setSelectedTab("chat"),
    },
    {
      icon: "pie-chart-outline",
      label: "Your wealth",
      onPress: () => app.setSelectedTab("invest"),
    },
    {
      icon: "wallet-outline",
      label: "Spending plan",
      onPress: () => {
        app.setChatPrefill("How is my spending tracking against my plan?");
        app.setSelectedTab("chat");
      },
    },
    {
      icon: "sparkles-outline",
      label: "What I've learned",
      onPress: () => app.setSelectedTab("profile"),
    },
  ];

  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      style={styles.carousel}
      contentContainerStyle={styles.pillRow}
    >
      {actions.map((a) => (
        <Pressable
          key={a.label}
          onPress={a.onPress}
          style={({ pressed }) => [styles.actionPill, pressed && { opacity: 0.7 }]}
        >
          <Ionicons name={a.icon} size={18} color={colors.allworthAccent} />
          <Text style={styles.actionLabel}>{a.label}</Text>
        </Pressable>
      ))}
    </ScrollView>
  );
}

function AccountsSnapshotCard({ d }: { d: Dashboard }) {
  const app = useApp();

  return (
    <Pressable
      onPress={() => app.setSelectedTab("invest")}
      style={({ pressed }) => [styles.snapshotCard, pressed && { opacity: 0.85 }]}
    >
      <SnapshotRow
        label="Allworth accounts"
        sublabel={`${d.accounts.allworth.length} accounts managed`}
        value={usd(d.allworthTotal)}
      />
      <HairlineDivider />
      <SnapshotRow
        label="Outside accounts we can see"
        sublabel="Held away — not yet part of your plan"
        value={usd(d.heldAwayTotal)}
      />
      <HairlineDivider />
      <SnapshotRow label="Liabilities" value={usd(d.liabilitiesTotal)} negative />
    </Pressable>
  );
}

function SnapshotRow({
  label,
  sublabel,
  value,
  negative,
}: {
  label: string;
  sublabel?: string;
  value: string;
  negative?: boolean;
}) {
  return (
    <View style={styles.snapshotRow}>
      <View style={{ flex: 1 }}>
        <Text style={styles.snapshotLabel}>{label}</Text>
        {sublabel ? <Text style={styles.snapshotSublabel}>{sublabel}</Text> : null}
      </View>
      <Text style={[styles.snapshotValue, negative && { color: colors.loss }]}>{value}</Text>
      <Ionicons name="chevron-forward" size={14} color={colors.inkTertiary} />
    </View>
  );
}

// Lead with the long-horizon trajectory, not a one-month dip. A client shouldn't
// log in to "you're down $7k this month" — over the year they're up, which is the
// frame a good advisor uses. The sparkline still shows the recent shape honestly.
function trajectory(d: Dashboard): { text: string; positive: boolean } | undefined {
  const h = d.netWorthHistory;
  if (h.length < 2) return undefined;
  const base = h[0].value;
  const diff = h[h.length - 1].value - base;
  const pct = base ? (diff / base) * 100 : 0;
  const sign = diff >= 0 ? "+" : "−";
  return {
    text: `${sign}${usd(Math.abs(diff))} (${sign}${Math.abs(pct).toFixed(1)}%) past year`,
    positive: diff >= 0,
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
      <Text style={styles.errorTitle}>Backend offline</Text>
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
  carousel: { marginHorizontal: -20 },
  carouselContent: { paddingHorizontal: 20, gap: 12, alignItems: "stretch" },
  pillRow: { paddingHorizontal: 20, gap: 10 },
  actionPill: {
    ...card,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 999,
  },
  actionLabel: { fontSize: 14, fontFamily: fonts.sansBold, color: colors.inkPrimary },
  snapshotCard: { ...card, paddingHorizontal: 16, paddingVertical: 6 },
  snapshotRow: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 13 },
  snapshotLabel: { fontSize: 15, fontFamily: fonts.sans, color: colors.inkPrimary },
  snapshotSublabel: {
    fontSize: 12,
    fontFamily: fonts.sans,
    color: colors.inkTertiary,
    marginTop: 2,
  },
  snapshotValue: {
    fontSize: 15,
    fontFamily: fonts.sansBold,
    color: colors.inkPrimary,
    fontVariant: ["tabular-nums"],
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
