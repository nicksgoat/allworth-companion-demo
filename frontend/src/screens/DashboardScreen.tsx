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
import * as Haptics from "expo-haptics";
import { RiseIn, useAnimatedValue } from "../anim";
import { APP_HEADER_HEIGHT, AppHeader, TAB_BAR_HEIGHT } from "../components/Glass";
import { NudgeCard } from "../components/NudgeCard";
import { DisclaimerFooter, SectionHeader } from "../components/Rows";
import { useApp } from "../state";
import { card, colors, fonts, radius, space, text, usd } from "../theme";
import type { Dashboard, Nudge } from "../types";
import { AdvisorConciergeSheet } from "./AdvisorConciergeSheet";
import { DocumentsSheet } from "./DocumentsSheet";
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
          paddingTop: insets.top + APP_HEADER_HEIGHT + 8,
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
      <AppHeader title="Home" scrollY={scrollY} />
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

// Home is a router, not a statement (stakeholder feedback): greeting, what
// needs attention, quick actions into chat and features. Numbers, charts, and
// totals live in Wealth — one tap away, never on the front door.
function DashboardContent({ d, onNudge }: { d: Dashboard; onNudge: (n: Nudge) => void }) {
  const app = useApp();
  const { width: winW } = useWindowDimensions();
  const nudgeW = Math.min(360, winW - 64); // fixed-width slides so the next card peeks
  const firstName = (d.client?.name ?? "Maya Tran").split(",")[0].split(" ")[0];
  const [conciergeOpen, setConciergeOpen] = useState(false);
  const [documentsOpen, setDocumentsOpen] = useState(false);

  const askChat = (prompt: string) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    app.setChatPrefill(prompt);
    app.setSelectedTab("chat");
  };

  // The outside-assets attention card is client-derived: allocation of
  // held-away money is exactly the kind of thing that "actually needs
  // attention", and its action is a conversation, not a dashboard.
  const heldAwayNudge: Nudge | null =
    d.heldAwayTotal > 0
      ? {
          id: "held-away-allocation",
          type: "allocation",
          title: "Outside assets",
          headline: `${usd(d.heldAwayTotal)} held away`,
          body: "",
          cta: "Ask what this means",
          advisorCta: "",
          severity: "info",
        }
      : null;

  const quickActions: { icon: keyof typeof Ionicons.glyphMap; label: string; go: () => void }[] = [
    {
      icon: "chatbubble-outline",
      label: "Ask about spending",
      go: () => askChat("How does this spending affect my plan?"),
    },
    {
      icon: "calendar-outline",
      label: `Book ${d.advisor?.name?.split(" ")[0] ?? "your advisor"}`,
      go: () => {
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
        setConciergeOpen(true);
      },
    },
    {
      icon: "flag-outline",
      label: "My goals",
      go: () => askChat("Am I on track for the lake house goal?"),
    },
    {
      icon: "folder-open-outline",
      label: "Documents",
      go: () => {
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
        setDocumentsOpen(true);
      },
    },
  ];

  return (
    <View style={{ gap: space[6] }}>
      <View style={styles.greetingBlock}>
        <Text style={styles.greetingLead}>{greetingForNow()},</Text>
        <Text style={styles.greetingName}>{firstName}</Text>
      </View>

      <RiseIn delay={40} style={{ gap: space[3] }}>
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
          {heldAwayNudge ? (
            <View key={heldAwayNudge.id} style={{ width: nudgeW }}>
              <NudgeCard
                nudge={heldAwayNudge}
                onPress={() =>
                  askChat("What should I be doing with the money I hold outside Allworth?")
                }
                fill
              />
            </View>
          ) : null}
        </ScrollView>
      </RiseIn>

      <RiseIn delay={140} style={{ gap: space[3] }}>
        <SectionHeader>Quick actions</SectionHeader>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={styles.carousel}
          contentContainerStyle={styles.carouselContent}
        >
          {quickActions.map((a) => (
            <Pressable
              key={a.label}
              onPress={a.go}
              style={({ pressed }) => [styles.quickAction, pressed && { opacity: 0.7 }]}
            >
              <Ionicons name={a.icon} size={18} color={colors.allworthNavy} />
              <Text style={styles.quickActionText}>{a.label}</Text>
            </Pressable>
          ))}
        </ScrollView>
      </RiseIn>

      <RiseIn delay={220}>
        <WealthGuideCard onPress={() => app.setSelectedTab("invest")} />
      </RiseIn>

      <View style={{ paddingVertical: space[2] }}>
        <DisclaimerFooter status={d.dataStatus} />
      </View>

      <AdvisorConciergeSheet
        visible={conciergeOpen}
        advisor={d.advisor}
        onClose={() => setConciergeOpen(false)}
      />
      <DocumentsSheet visible={documentsOpen} onClose={() => setDocumentsOpen(false)} />
    </View>
  );
}

// The guide to the numbers — no totals on the front door, just the door.
function WealthGuideCard({ onPress }: { onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [styles.summaryLine, pressed && { opacity: 0.7 }]}
    >
      <Ionicons name="pie-chart-outline" size={18} color={colors.allworthAccent} />
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={styles.summaryText}>Your wealth</Text>
        <Text style={styles.summarySub}>Accounts, allocation, and what's held away</Text>
      </View>
      <Ionicons name="chevron-forward" size={16} color={colors.inkTertiary} />
    </Pressable>
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
  summaryText: { ...text.body, fontFamily: fonts.sansBold },
  summarySub: { ...text.caption },
  greetingBlock: { gap: 2, paddingTop: space[2] },
  greetingLead: { ...text.body, color: colors.inkSecondary },
  greetingName: { fontFamily: fonts.displayMedium, fontSize: 34, color: colors.inkPrimary },
  quickAction: {
    ...card,
    flexDirection: "row",
    alignItems: "center",
    gap: space[2],
    paddingHorizontal: space[4],
    paddingVertical: space[3],
    borderRadius: radius.pill,
  },
  quickActionText: { fontSize: 14, fontFamily: fonts.sansBold, color: colors.allworthNavy },
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
