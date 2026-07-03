import { Ionicons } from "@expo/vector-icons";
import { useNavigation } from "@react-navigation/native";
import { createNativeStackNavigator, NativeStackScreenProps } from "@react-navigation/native-stack";
import React, { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { HeroNumber } from "../components/HeroNumber";
import {
  AccountRow,
  DisclaimerFooter,
  HairlineDivider,
  SectionHeader,
} from "../components/Rows";
import { APP_HEADER_HEIGHT, AppHeader } from "../components/Glass";
import { AdvisorConversationView } from "./AdvisorConversationScreen";
import { useApp } from "../state";
import { card, colors, fonts, radius, space, text, usd } from "../theme";
import type { AdvisorBrief, BookResponse, ConversationMessage, Household } from "../types";

type AdvisorStackParams = {
  Book: undefined;
  ClientDetail: { household: Household };
  ClientConversation: { household: Household };
};

const Stack = createNativeStackNavigator<AdvisorStackParams>();

export function AdvisorNavigator() {
  return (
    <Stack.Navigator id="AdvisorStack" screenOptions={{ headerTintColor: colors.allworthNavy }}>
      <Stack.Screen name="Book" component={BookScreen} options={{ headerShown: false }} />
      <Stack.Screen
        name="ClientDetail"
        component={ClientDetailScreen}
        options={({ route }) => ({ title: route.params.household.name, headerBackTitle: "Book" })}
      />
      <Stack.Screen
        name="ClientConversation"
        component={ClientConversationScreen}
        options={({ route }) => ({
          title: `${route.params.household.name.split(",")[0].split(" ")[0]}'s conversation`,
          headerBackTitle: "Client",
        })}
      />
    </Stack.Navigator>
  );
}

function ClientConversationScreen({
  route,
}: NativeStackScreenProps<AdvisorStackParams, "ClientConversation">) {
  const { household } = route.params;
  return (
    <AdvisorConversationView
      clientId={household.clientId}
      clientName={household.name.split(",")[0].split(" ")[0]}
    />
  );
}

function BookScreen() {
  const app = useApp();
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<any>();
  const [book, setBook] = useState<BookResponse | null>(null);
  const autoPushed = useRef(false);

  useEffect(() => {
    const advisorId = app.dashboard?.advisor?.id ?? "nicole";
    app.api
      .book(advisorId)
      .then(setBook)
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (app.demoScreen === "advisor_detail" && book && !autoPushed.current) {
      const maya = book.households.find((h) => h.clientId === "maya");
      if (maya) {
        autoPushed.current = true;
        app.clearDemoScreen();
        navigation.navigate("ClientDetail", { household: maya });
      }
    }
  }, [book, app.demoScreen]);

  return (
    <>
    <ScrollView
      style={{ backgroundColor: colors.surfacePrimary }}
      contentContainerStyle={{ padding: 20, paddingTop: insets.top + APP_HEADER_HEIGHT + 8, gap: 20 }}
    >
      {book ? (
        <Text style={styles.subtitle}>
          {book.advisor.name} · {book.advisor.title}
        </Text>
      ) : null}

      {book ? (
        <View>
          {book.households.map((household, i) => (
            <React.Fragment key={household.clientId}>
              {i > 0 ? <HairlineDivider /> : null}
              <HouseholdRow
                household={household}
                onPress={() => navigation.navigate("ClientDetail", { household })}
              />
            </React.Fragment>
          ))}
        </View>
      ) : (
        <ActivityIndicator style={{ paddingTop: 80 }} />
      )}

      <View style={{ paddingVertical: 8 }}>
        <DisclaimerFooter />
      </View>
    </ScrollView>
    <AppHeader
      title="Your book"
      action={{ icon: "swap-horizontal-outline", onPress: () => app.setMode("client") }}
    />
    </>
  );
}

function HouseholdRow({ household, onPress }: { household: Household; onPress: () => void }) {
  // Skip the "&" in couple names: "Robert & Elaine Castillo" → RE, not R&.
  const initials = household.name
    .split(" ")
    .filter((w) => /^[A-Za-z]/.test(w))
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
  const highlight = household.highlight === true;
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [styles.householdRow, pressed && { opacity: 0.7 }]}
    >
      <View
        style={[
          styles.householdAvatar,
          { backgroundColor: highlight ? colors.allworthNavy : colors.inkFaint },
        ]}
      >
        <Text
          style={[styles.householdInitials, { color: highlight ? "#fff" : colors.inkSecondary }]}
        >
          {initials}
        </Text>
      </View>
      <View style={{ flex: 1, gap: 3 }}>
        <Text style={[styles.householdName, highlight && { fontFamily: fonts.sansBold }]}>
          {household.name}
        </Text>
        <View style={{ flexDirection: "row", gap: 8 }}>
          <Text style={styles.householdManaged}>{usd(household.managedAssets)} managed</Text>
          {household.heldAwayDetected > 0 ? (
            <Text style={styles.householdHeldAway}>
              {usd(household.heldAwayDetected)} held away
            </Text>
          ) : null}
        </View>
      </View>
      {household.openNudges > 0 ? (
        <View style={styles.nudgeBadge}>
          <Text style={styles.nudgeBadgeText}>{household.openNudges}</Text>
        </View>
      ) : null}
      <Ionicons name="chevron-forward" size={15} color={colors.inkTertiary} />
    </Pressable>
  );
}

function ClientDetailScreen({ route }: NativeStackScreenProps<AdvisorStackParams, "ClientDetail">) {
  const app = useApp();
  const { household } = route.params;
  const [brief, setBrief] = useState<AdvisorBrief | null>(null);

  useEffect(() => {
    const advisorId = app.dashboard?.advisor?.id ?? "nicole";
    app.api
      .brief(advisorId, household.clientId)
      .then(setBrief)
      .catch(() => {});
  }, [household.clientId]);

  return (
    <ScrollView
      style={{ backgroundColor: colors.surfacePrimary }}
      contentContainerStyle={{ padding: 20, gap: 24 }}
    >
      {brief ? (
        <>
          <View style={{ gap: 4 }}>
            <HeroNumber label="Held away — detected" value={brief.heldAwayDetected} />
            <Text style={styles.managedCaption}>alongside {usd(brief.managedTotal)} managed</Text>
          </View>

          <View>
            <View style={{ paddingBottom: 4 }}>
              <SectionHeader>Outside accounts</SectionHeader>
            </View>
            {[...brief.heldAwayAccounts, ...brief.liabilities].map((account, i) => (
              <React.Fragment key={account.id}>
                {i > 0 ? <HairlineDivider /> : null}
                <AccountRow account={account} />
              </React.Fragment>
            ))}
          </View>

          <View style={styles.briefCard}>
            <View style={styles.briefHeader}>
              <Ionicons name="sparkles" size={12} color={colors.allworthAccent} />
              <SectionHeader>Auto-prepared brief</SectionHeader>
            </View>
            {brief.narrative.split("\n").map((paragraph, i) => (
              <Text key={i} style={styles.briefText}>
                {paragraph}
              </Text>
            ))}
          </View>

          <ConversationPreviewCard household={household} />

          {brief.reviewWorkflow ? (
            <ReviewWorkflowCard workflow={brief.reviewWorkflow} />
          ) : null}
        </>
      ) : (
        <ActivityIndicator style={{ paddingTop: 100 }} />
      )}
      <View style={{ paddingVertical: 8 }}>
        <DisclaimerFooter />
      </View>
    </ScrollView>
  );
}

// Compact entry point to the full-screen conversation: the last exchange at a
// glance, then push into AdvisorConversationView to read and interject.
function ConversationPreviewCard({ household }: { household: Household }) {
  const app = useApp();
  const navigation = useNavigation<any>();
  const clientName = household.name.split(",")[0].split(" ")[0];
  const [messages, setMessages] = useState<ConversationMessage[]>([]);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const res = await app.api.conversation(household.clientId, app.session);
        if (!cancelled) setMessages(res.messages);
      } catch {}
    };
    tick();
    const interval = setInterval(tick, 4000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [household.clientId, app.session]);

  const recent = messages.slice(-3);
  const speaker = (m: ConversationMessage) =>
    m.role === "advisor"
      ? (m.advisorName ?? "You").split(" ")[0]
      : m.role === "user"
        ? clientName
        : "Assistant";

  return (
    <Pressable
      onPress={() => navigation.navigate("ClientConversation", { household })}
      style={({ pressed }) => [styles.briefCard, pressed && { opacity: 0.8 }]}
    >
      <View style={styles.briefHeader}>
        <Ionicons name="chatbubbles-outline" size={13} color={colors.allworthAccent} />
        <SectionHeader>Live conversation</SectionHeader>
        <View style={{ flex: 1 }} />
        {messages.length > 0 ? (
          <Text style={styles.convoCount}>{messages.length} messages</Text>
        ) : null}
      </View>

      {recent.length === 0 ? (
        <Text style={styles.convoEmpty}>
          No thread yet — {clientName}'s next assistant chat will appear here.
        </Text>
      ) : (
        recent.map((m) => (
          <View key={`${m.seq}-${m.id ?? "t"}`} style={styles.convoPreviewRow}>
            <Text
              style={[styles.convoSpeaker, m.role === "advisor" && styles.convoSpeakerAdvisor]}
            >
              {speaker(m)}
            </Text>
            <Text style={styles.convoPreviewText} numberOfLines={1}>
              {m.text}
            </Text>
          </View>
        ))
      )}

      <View style={styles.convoOpenRow}>
        <Text style={styles.convoOpenText}>Open conversation</Text>
        <Ionicons name="arrow-forward" size={15} color={colors.allworthAccent} />
      </View>
    </Pressable>
  );
}

function ReviewWorkflowCard({
  workflow,
}: {
  workflow: NonNullable<AdvisorBrief["reviewWorkflow"]>;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <View style={styles.briefCard}>
      <View style={styles.briefHeader}>
        <Ionicons name="checkmark-done" size={13} color={colors.allworthAccent} />
        <SectionHeader>Advisor review workflow</SectionHeader>
      </View>

      {/* Lead with the summary + the single next-best-action, prominently. */}
      <Text style={styles.workflowSummary}>{workflow.summary}</Text>
      <View style={styles.nextActionRow}>
        <Ionicons name="arrow-forward-circle" size={16} color={colors.allworthAccent} />
        <Text style={styles.nextActionText}>{workflow.nextBestAction}</Text>
      </View>

      <HairlineDivider />

      {/* Details collapse behind a tap so the card reads as summary-first. */}
      <Pressable
        onPress={() => setExpanded((v) => !v)}
        hitSlop={6}
        style={({ pressed }) => [styles.expandToggle, pressed && { opacity: 0.6 }]}
      >
        <Text style={text.sectionLabel}>
          {expanded ? "Hide review detail" : "Review detail"}
        </Text>
        <Ionicons
          name={expanded ? "chevron-up" : "chevron-down"}
          size={14}
          color={colors.inkTertiary}
        />
      </Pressable>

      {expanded ? (
        <View style={styles.workflowDetail}>
          <BulletList title="Decisions to review">
            {workflow.decisionsToReview.map((item) => (
              <View key={item.id} style={styles.bulletRow}>
                <View style={styles.bulletDot} />
                <View style={{ flex: 1, gap: space[1] }}>
                  <Text style={styles.bulletTitle}>{item.label}</Text>
                  <Text style={styles.bulletBody}>{item.whyItMatters}</Text>
                </View>
              </View>
            ))}
          </BulletList>
          <BulletList title="Talking points">
            {workflow.talkingPoints.map((item) => (
              <Bullet key={item}>{item}</Bullet>
            ))}
          </BulletList>
          <BulletList title="Open questions">
            {workflow.openQuestions.map((item) => (
              <Bullet key={item}>{item}</Bullet>
            ))}
          </BulletList>
        </View>
      ) : null}
    </View>
  );
}

// A simple labeled bullet group — no inner bordered sub-card.
function BulletList({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.bulletGroup}>
      <Text style={text.sectionLabel}>{title}</Text>
      {children}
    </View>
  );
}

function Bullet({ children }: { children: React.ReactNode }) {
  return (
    <View style={styles.bulletRow}>
      <View style={styles.bulletDot} />
      <Text style={styles.bulletText}>{children}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  headerRow: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between" },
  title: { fontSize: 28, fontFamily: fonts.display, color: colors.inkPrimary },
  subtitle: { fontSize: 13, fontFamily: fonts.sans, color: colors.inkSecondary },
  householdRow: { flexDirection: "row", alignItems: "center", gap: 12, paddingVertical: 12 },
  householdAvatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
  },
  householdInitials: { fontSize: 14, fontFamily: fonts.sansBold },
  householdName: { fontSize: 17, fontFamily: fonts.sans, color: colors.inkPrimary },
  householdManaged: { fontSize: 13, fontFamily: fonts.sans, color: colors.inkTertiary },
  householdHeldAway: { fontSize: 13, fontFamily: fonts.sansBold, color: colors.allworthAccent },
  nudgeBadge: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: colors.attention,
    alignItems: "center",
    justifyContent: "center",
  },
  nudgeBadgeText: { color: "#fff", fontSize: 13, fontFamily: fonts.sansBold },
  managedCaption: {
    fontSize: 15,
    fontFamily: fonts.sans,
    color: colors.inkSecondary,
    fontVariant: ["tabular-nums"],
  },
  briefCard: { ...card, padding: space[4], gap: space[3] },
  briefHeader: { flexDirection: "row", alignItems: "center", gap: space[2] },
  briefText: { ...text.body, lineHeight: 22 },
  // Live-conversation preview: three one-liners + the open affordance.
  convoEmpty: { ...text.bodySm, color: colors.inkTertiary },
  convoCount: { fontSize: 11, fontFamily: fonts.sans, color: colors.inkTertiary },
  convoPreviewRow: { flexDirection: "row", alignItems: "baseline", gap: space[2] },
  convoSpeaker: {
    fontSize: 11,
    fontFamily: fonts.sansBold,
    color: colors.inkTertiary,
    letterSpacing: 0.4,
    textTransform: "uppercase",
  },
  convoSpeakerAdvisor: { color: colors.allworthAccent },
  convoPreviewText: { ...text.bodySm, color: colors.inkSecondary, flex: 1 },
  convoOpenRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: space[2],
    paddingTop: space[1],
  },
  convoOpenText: { fontSize: 14, fontFamily: fonts.sansBold, color: colors.allworthAccent },
  workflowSummary: { ...text.body, lineHeight: 22 },
  nextActionRow: { flexDirection: "row", alignItems: "center", gap: space[2] },
  nextActionText: { flex: 1, fontFamily: fonts.sansBold, fontSize: 15, color: colors.allworthAccent },
  expandToggle: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  workflowDetail: { gap: space[5] },
  bulletGroup: { gap: space[2] },
  bulletRow: { flexDirection: "row", alignItems: "flex-start", gap: space[2] },
  bulletDot: {
    width: 5,
    height: 5,
    borderRadius: radius.pill,
    backgroundColor: colors.allworthAccent,
    marginTop: 7,
  },
  bulletText: { ...text.body, flex: 1, lineHeight: 21 },
  bulletTitle: { fontFamily: fonts.sansBold, fontSize: 15, color: colors.inkPrimary },
  bulletBody: { ...text.bodySm, lineHeight: 19 },
});
