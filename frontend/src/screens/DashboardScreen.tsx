import { Ionicons } from "@expo/vector-icons";
import React, { useEffect, useState } from "react";
import {
  Animated,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import { RiseIn, useAnimatedValue } from "../anim";
import { APP_HEADER_HEIGHT, AppHeader, TAB_BAR_HEIGHT } from "../components/Glass";
import { GreetingHero } from "../components/GreetingHero";
import { DisclaimerFooter, SectionHeader } from "../components/Rows";
import { useApp } from "../state";
import { card, colors, fonts, radius, space, text, usd } from "../theme";
import type { Dashboard, Nudge } from "../types";
import { AdvisorConciergeSheet } from "./AdvisorConciergeSheet";
import { DocumentsSheet } from "./DocumentsSheet";
import { GoalsSheet } from "./GoalsSheet";
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
      <AppHeader title="Home" scrollY={scrollY} onHero />
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
// needs attention, quick actions into chat and features, the advisor within
// reach. Numbers, charts, and totals live in Wealth — one tap away, never on
// the front door. Composition is calm: full-width rows and a grid, nothing
// cropped, nothing shouting.
function DashboardContent({ d, onNudge }: { d: Dashboard; onNudge: (n: Nudge) => void }) {
  const app = useApp();
  const firstName = (d.client?.name ?? "Maya Tran").split(",")[0].split(" ")[0];
  const advisorFirst = d.advisor?.name?.split(" ")[0] ?? "your advisor";
  const [conciergeOpen, setConciergeOpen] = useState(false);
  const [documentsOpen, setDocumentsOpen] = useState(false);
  const [goalsOpen, setGoalsOpen] = useState(false);

  const askChat = (prompt: string) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    app.setChatPrefill(prompt);
    app.setSelectedTab("chat");
  };

  const quickActions: { icon: keyof typeof Ionicons.glyphMap; label: string; go: () => void }[] = [
    {
      icon: "chatbubble-outline",
      label: "Ask about spending",
      go: () => askChat("How does this spending affect my plan?"),
    },
    {
      icon: "flag-outline",
      label: "My goals",
      go: () => {
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
        setGoalsOpen(true);
      },
    },
    {
      icon: "calendar-outline",
      label: `Book ${advisorFirst}`,
      go: () => {
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
        setConciergeOpen(true);
      },
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
      <GreetingHero
        greeting={greetingForNow()}
        name={firstName}
        advisorLine={d.advisor ? `${d.advisor.name} · your advisor` : "your advisor"}
        onOpenWealth={() => app.setSelectedTab("invest")}
      />

      <RiseIn delay={40} style={{ gap: space[3] }}>
        <SectionHeader>Needs your attention</SectionHeader>
        <View style={styles.attentionCard}>
          {d.nudges.map((nudge, i) => (
            <React.Fragment key={nudge.id}>
              {i > 0 ? <View style={styles.attentionDivider} /> : null}
              <AttentionRow
                icon={nudge.type === "concentration" ? "pie-chart-outline" : "trending-up-outline"}
                tone={nudge.severity === "info" ? "info" : "attention"}
                title={nudge.title}
                sub={nudge.headline}
                onPress={() => onNudge(nudge)}
              />
            </React.Fragment>
          ))}
          {d.heldAwayTotal > 0 ? (
            <>
              {d.nudges.length > 0 ? <View style={styles.attentionDivider} /> : null}
              <AttentionRow
                icon="wallet-outline"
                tone="info"
                title="Money held outside your plan"
                sub={`${usd(d.heldAwayTotal)} held away — worth a conversation`}
                onPress={() =>
                  askChat("What should I be doing with the money I hold outside Allworth?")
                }
              />
            </>
          ) : null}
        </View>
      </RiseIn>

      <RiseIn delay={140} style={{ gap: space[3] }}>
        <SectionHeader>Quick actions</SectionHeader>
        <View style={styles.actionGrid}>
          {quickActions.map((a) => (
            <Pressable
              key={a.label}
              onPress={a.go}
              style={({ pressed }) => [styles.quickAction, pressed && { opacity: 0.7 }]}
            >
              <Ionicons name={a.icon} size={18} color={colors.allworthNavy} />
              <Text style={styles.quickActionText} numberOfLines={1}>
                {a.label}
              </Text>
            </Pressable>
          ))}
        </View>
      </RiseIn>

      <RiseIn delay={220} style={{ gap: space[3] }}>
        <SectionHeader>Your advisor</SectionHeader>
        <View style={styles.advisorCard}>
          <View style={styles.advisorAvatar}>
            <Text style={styles.advisorAvatarText}>{d.advisor?.avatarInitials ?? "A"}</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.advisorName}>{d.advisor?.name ?? "Your advisor"}</Text>
            <Text style={styles.advisorTitle}>{d.advisor?.title ?? ""}</Text>
          </View>
          <Pressable
            onPress={() => askChat(`Can you have ${advisorFirst} reach out to me?`)}
            hitSlop={8}
            style={({ pressed }) => [styles.advisorBtn, pressed && { opacity: 0.8 }]}
          >
            <Ionicons name="chatbubble-ellipses" size={18} color={colors.allworthAccent} />
          </Pressable>
          <Pressable
            onPress={() => {
              Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
              setConciergeOpen(true);
            }}
            hitSlop={8}
            style={({ pressed }) => [styles.advisorBtn, pressed && { opacity: 0.8 }]}
          >
            <Ionicons name="calendar-outline" size={18} color={colors.allworthAccent} />
          </Pressable>
        </View>
      </RiseIn>

      <RiseIn delay={300}>
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
      <GoalsSheet visible={goalsOpen} onClose={() => setGoalsOpen(false)} />
    </View>
  );
}

// One calm row per attention item: tinted icon chip, plain-English line,
// detail line, chevron. No hero numerals, nothing orange screaming.
function AttentionRow({
  icon,
  tone,
  title,
  sub,
  onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  tone: "attention" | "info";
  title: string;
  sub: string;
  onPress: () => void;
}) {
  const tint = tone === "attention" ? colors.attention : colors.allworthAccent;
  const wash = tone === "attention" ? "rgba(210,109,55,0.10)" : "rgba(62,113,183,0.10)";
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [styles.attentionRow, pressed && { opacity: 0.7 }]}
    >
      <View style={[styles.attentionIcon, { backgroundColor: wash }]}>
        <Ionicons name={icon} size={17} color={tint} />
      </View>
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={styles.attentionTitle} numberOfLines={2}>
          {title}
        </Text>
        <Text style={styles.attentionSub} numberOfLines={1}>
          {sub}
        </Text>
      </View>
      <Ionicons name="chevron-forward" size={15} color={colors.inkTertiary} />
    </Pressable>
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
  attentionCard: { ...card, paddingHorizontal: space[4], paddingVertical: space[1] },
  attentionRow: { flexDirection: "row", alignItems: "center", gap: space[3], paddingVertical: space[3] },
  attentionDivider: { height: StyleSheet.hairlineWidth, backgroundColor: colors.hairline },
  attentionIcon: {
    width: 34,
    height: 34,
    borderRadius: radius.chip,
    alignItems: "center",
    justifyContent: "center",
  },
  attentionTitle: { fontSize: 15, fontFamily: fonts.sansBold, color: colors.inkPrimary },
  attentionSub: { ...text.caption, color: colors.inkSecondary },
  actionGrid: { flexDirection: "row", flexWrap: "wrap", gap: space[3] },
  advisorCard: {
    ...card,
    flexDirection: "row",
    alignItems: "center",
    gap: space[3],
    padding: space[4],
  },
  advisorAvatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.allworthNavy,
    alignItems: "center",
    justifyContent: "center",
  },
  advisorAvatarText: { fontSize: 15, fontFamily: fonts.sansBold, color: "#FFFFFF", letterSpacing: 0.5 },
  advisorName: { fontSize: 16, fontFamily: fonts.sansBold, color: colors.inkPrimary },
  advisorTitle: { fontSize: 13, fontFamily: fonts.sans, color: colors.inkSecondary, marginTop: 1 },
  advisorBtn: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: "rgba(62,113,183,0.12)",
    alignItems: "center",
    justifyContent: "center",
  },
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
  quickAction: {
    ...card,
    flexDirection: "row",
    alignItems: "center",
    gap: space[2],
    paddingHorizontal: space[3],
    paddingVertical: space[3],
    borderRadius: radius.card,
    flexBasis: "47%",
    flexGrow: 1,
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
    backgroundColor: colors.allworthNavy,
    paddingHorizontal: 18,
    paddingVertical: 10,
    borderRadius: 10,
  },
  retryText: { color: "#fff", fontSize: 15, fontFamily: fonts.sansBold },
});
