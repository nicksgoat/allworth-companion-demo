import { Ionicons } from "@expo/vector-icons";
import React, { useEffect, useState } from "react";
import { Animated, Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";
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
  const fullName = d.client?.name ?? "Maya Tran";
  const initials = d.client?.avatarInitials ?? "MT";
  return (
    <View style={{ gap: 24 }}>
      <NetWorthHero
        greeting={greetingForNow()}
        name={fullName}
        initials={initials}
        netWorth={d.netWorth}
        delta={trajectory(d)}
        history={d.netWorthHistory}
        insetsTop={insets.top}
        onOpenWealth={() => app.setSelectedTab("invest")}
        onAvatarPress={() => app.setSelectedTab("profile")}
      />

      {d.nudges.length ? (
        <View style={{ gap: 12 }}>
          <SectionHeader>Needs your attention</SectionHeader>
          {d.nudges.slice(0, 2).map((nudge, i) => (
            <RiseIn key={nudge.id} delay={80 + i * 60}>
              <NudgeCard nudge={nudge} onPress={() => onNudge(nudge)} />
            </RiseIn>
          ))}
        </View>
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
    <View style={styles.actionsGrid}>
      {actions.map((a) => (
        <Pressable
          key={a.label}
          onPress={a.onPress}
          style={({ pressed }) => [styles.actionCard, pressed && { opacity: 0.7 }]}
        >
          <Ionicons name={a.icon} size={20} color={colors.allworthAccent} />
          <Text style={styles.actionLabel}>{a.label}</Text>
        </Pressable>
      ))}
    </View>
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
  actionsGrid: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  actionCard: {
    ...card,
    flexBasis: "46%",
    flexGrow: 1,
    padding: 14,
    gap: 8,
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
