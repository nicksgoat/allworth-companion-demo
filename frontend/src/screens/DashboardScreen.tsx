import { Ionicons } from "@expo/vector-icons";
import React, { useEffect, useState } from "react";
import { Animated, Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { RiseIn, useAnimatedValue, useCountUp } from "../anim";
import { GlassHeader, TAB_BAR_HEIGHT } from "../components/Glass";
import { NudgeCard } from "../components/NudgeCard";
import { DisclaimerFooter, HairlineDivider, SectionHeader } from "../components/Rows";
import { Sparkline } from "../components/Sparkline";
import { AllworthWordmark } from "../components/Wordmark";
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
  const firstName = d.client?.name.split(" ")[0] ?? "Maya";
  return (
    <View style={{ gap: 24 }}>
      <View style={styles.headerRow}>
        <Text style={styles.greeting} numberOfLines={1} adjustsFontSizeToFit>
          {greetingForNow()}, {firstName}
        </Text>
        <AllworthWordmark />
      </View>

      <RiseIn>
        <NetWorthCard d={d} />
      </RiseIn>

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

function NetWorthCard({ d }: { d: Dashboard }) {
  const app = useApp();
  const displayed = useCountUp(d.netWorth);
  const delta = monthDelta(d);

  return (
    <Pressable
      onPress={() => app.setSelectedTab("invest")}
      style={({ pressed }) => [styles.nwCard, pressed && { opacity: 0.85 }]}
    >
      <SectionHeader>Net worth</SectionHeader>
      <Text style={styles.nwValue}>{usd(displayed)}</Text>
      {delta ? (
        <Text style={[styles.nwDelta, { color: delta.positive ? colors.gain : colors.loss }]}>
          {delta.text}
        </Text>
      ) : null}
      <Sparkline points={d.netWorthHistory} />
      <View style={styles.nwLink}>
        <Text style={styles.nwLinkText}>View your wealth</Text>
        <Ionicons name="chevron-forward" size={14} color={colors.allworthAccent} />
      </View>
    </Pressable>
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

function monthDelta(d: Dashboard): { text: string; positive: boolean } | undefined {
  const h = d.netWorthHistory;
  if (h.length < 2) return undefined;
  const diff = h[h.length - 1].value - h[h.length - 2].value;
  return { text: `${diff >= 0 ? "+" : ""}${usd(diff)} this month`, positive: diff >= 0 };
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
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  greeting: { fontSize: 28, fontFamily: fonts.display, color: colors.inkPrimary, flexShrink: 1 },
  nwCard: { ...card, padding: 16, gap: 6 },
  nwValue: {
    fontSize: 34,
    fontFamily: fonts.displayMedium,
    color: colors.inkPrimary,
    fontVariant: ["tabular-nums"],
  },
  nwDelta: { fontSize: 14, fontFamily: fonts.sansBold, fontVariant: ["tabular-nums"] },
  nwLink: { flexDirection: "row", alignItems: "center", gap: 2, paddingTop: 4 },
  nwLinkText: { fontSize: 14, fontFamily: fonts.sansBold, color: colors.allworthAccent },
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
