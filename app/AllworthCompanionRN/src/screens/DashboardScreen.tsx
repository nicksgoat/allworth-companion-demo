import React, { useEffect, useState } from "react";
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { AdvisorHandoffCard } from "../components/AdvisorHandoffCard";
import { HeroNumber } from "../components/HeroNumber";
import { NudgeCard } from "../components/NudgeCard";
import { AccountRow, DisclaimerFooter, HairlineDivider, SectionHeader } from "../components/Rows";
import { Sparkline } from "../components/Sparkline";
import { AllworthWordmark } from "../components/Wordmark";
import { useApp } from "../state";
import { colors, usd } from "../theme";
import type { Account, Dashboard, Nudge } from "../types";
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

  return (
    <>
      <ScrollView
        style={{ backgroundColor: colors.surfacePrimary }}
        contentContainerStyle={{ padding: 20, paddingTop: insets.top + 8 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
      >
        {d ? (
          <DashboardContent d={d} onNudge={setSelectedNudge} />
        ) : app.dashboardError ? (
          <ErrorState message={app.dashboardError} onRetry={app.loadDashboard} />
        ) : (
          <Skeleton />
        )}
      </ScrollView>
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
        <Text style={styles.greeting}>{greetingForNow()}, {firstName}</Text>
        <AllworthWordmark />
      </View>

      <View style={{ gap: 14 }}>
        <HeroNumber label="Net worth" value={d.netWorth} delta={monthDelta(d)} />
        <Sparkline points={d.netWorthHistory} />
      </View>

      {d.nudges.slice(0, 2).map((nudge) => (
        <NudgeCard key={nudge.id} nudge={nudge} onPress={() => onNudge(nudge)} />
      ))}

      <AccountSection header="Allworth accounts" accounts={d.accounts.allworth} />
      <AccountSection
        header="Outside accounts we can see"
        accounts={d.accounts.outside}
        caption={`${usd(d.heldAwayTotal)} held away`}
      />

      <View style={{ paddingVertical: 8 }}>
        <DisclaimerFooter />
      </View>
    </View>
  );
}

function AccountSection({ header, accounts, caption }: { header: string; accounts: Account[]; caption?: string }) {
  return (
    <View>
      <View style={styles.sectionRow}>
        <SectionHeader>{header}</SectionHeader>
        {caption ? <Text style={styles.sectionCaption}>{caption}</Text> : null}
      </View>
      {accounts.map((account, i) => (
        <React.Fragment key={account.id}>
          {i > 0 ? <HairlineDivider /> : null}
          <AccountRow account={account} />
        </React.Fragment>
      ))}
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
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  greeting: { fontSize: 28, fontWeight: "600", color: colors.inkPrimary },
  sectionRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingBottom: 4 },
  sectionCaption: { fontSize: 13, color: colors.inkSecondary, fontVariant: ["tabular-nums"] },
  skeletonBlock: { height: 72, borderRadius: 12, backgroundColor: colors.inkFaint },
  errorBox: { alignItems: "center", paddingTop: 120, gap: 10, paddingHorizontal: 20 },
  errorTitle: { fontSize: 20, fontWeight: "600", color: colors.inkPrimary },
  errorMessage: { fontSize: 15, color: colors.inkSecondary, textAlign: "center" },
  retryButton: {
    marginTop: 6,
    backgroundColor: colors.allworthAccent,
    paddingHorizontal: 18,
    paddingVertical: 10,
    borderRadius: 10,
  },
  retryText: { color: "#fff", fontSize: 15, fontWeight: "600" },
});
