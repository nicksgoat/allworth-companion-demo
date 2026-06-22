import { Ionicons } from "@expo/vector-icons";
import React, { useCallback, useEffect, useState } from "react";
import { Animated, Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useAnimatedValue } from "../anim";
import { GlassHeader, TAB_BAR_HEIGHT } from "../components/Glass";
import {
  DisclaimerFooter,
  HairlineDivider,
  LearnedFactRow,
  SectionHeader,
} from "../components/Rows";
import { useAuth } from "../auth";
import { useApp } from "../state";
import { card, colors, fonts } from "../theme";
import type { LearnedFact } from "../types";
import { FactDetailSheet } from "./FactDetailSheet";

const CATEGORY_LABELS: Record<string, string> = {
  goals: "Your goals",
  preferences: "Your preferences",
  concerns: "On your mind",
  liquidity_events: "Decisions in motion",
  outside_assets_mentioned: "Accounts you've mentioned",
  life_events: "Life events",
};

export function ProfileScreen() {
  const app = useApp();
  const { session: authSession, logout } = useAuth();
  const insets = useSafeAreaInsets();
  const [facts, setFacts] = useState<LearnedFact[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedFact, setSelectedFact] = useState<LearnedFact | null>(null);
  const scrollY = useAnimatedValue(0);

  const client = app.dashboard?.client;
  const advisor = app.dashboard?.advisor;
  const name = client?.name ?? "Maya Tran";
  const initials = client?.avatarInitials ?? "MT";
  const meta = [client?.city, client?.age ? `Age ${client.age}` : null]
    .filter(Boolean)
    .join("  ·  ");

  const load = useCallback(async () => {
    try {
      setFacts((await app.api.profile(app.clientId)).facts);
    } catch {}
  }, [app.api, app.clientId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (app.demoScreen === "fact" && facts.length) {
      setSelectedFact(facts[0]);
      app.clearDemoScreen();
    }
  }, [app.demoScreen, facts]);

  const refresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const messageAdvisor = () => {
    const first = advisor?.name?.split(" ")[0] ?? "my advisor";
    app.setChatPrefill(`Can you have ${first} reach out to me?`);
    app.setSelectedTab("chat");
  };

  const categories = facts.reduce<string[]>(
    (seen, f) => (seen.includes(f.category) ? seen : [...seen, f.category]),
    [],
  );

  return (
    <>
      <Animated.ScrollView
        style={{ backgroundColor: colors.surfacePrimary }}
        contentContainerStyle={{
          padding: 20,
          paddingTop: insets.top + 8,
          paddingBottom: TAB_BAR_HEIGHT + insets.bottom + 24,
          gap: 24,
        }}
        onScroll={Animated.event([{ nativeEvent: { contentOffset: { y: scrollY } } }], {
          useNativeDriver: false,
        })}
        scrollEventThrottle={16}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
      >
        {/* Identity */}
        <View style={styles.identity}>
          <View style={styles.bigAvatar}>
            <Text style={styles.bigAvatarText}>{initials}</Text>
          </View>
          <Text style={styles.name}>{name}</Text>
          {meta ? <Text style={styles.meta}>{meta}</Text> : null}
        </View>

        {/* Advisor */}
        {advisor ? (
          <View style={{ gap: 8 }}>
            <SectionHeader>Your advisor</SectionHeader>
            <View style={styles.advisorCard}>
              <View style={styles.advisorAvatar}>
                <Text style={styles.advisorAvatarText}>{advisor.avatarInitials}</Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.advisorName}>{advisor.name}</Text>
                <Text style={styles.advisorTitle}>{advisor.title}</Text>
              </View>
              <Pressable
                onPress={messageAdvisor}
                hitSlop={8}
                style={({ pressed }) => [styles.advisorBtn, pressed && { opacity: 0.8 }]}
              >
                <Ionicons name="chatbubble-ellipses" size={18} color={colors.allworthAccent} />
              </Pressable>
            </View>
          </View>
        ) : null}

        {/* What I've learned (the AI's memory) */}
        <View style={{ gap: 10 }}>
          <SectionHeader>What I{"'"}ve learned</SectionHeader>
          <Text style={styles.subtitle}>
            Everything here came from you — each fact carries a source, a timestamp, and an audit
            trail. Tap any to see why I know it, or to remove it.
          </Text>

          {categories.map((category) => (
            <View key={category} style={styles.factGroup}>
              <Text style={styles.factGroupLabel}>{CATEGORY_LABELS[category] ?? category}</Text>
              {facts
                .filter((f) => f.category === category)
                .map((fact, i) => (
                  <React.Fragment key={fact.id}>
                    {i > 0 ? <HairlineDivider /> : null}
                    <Pressable
                      onPress={() => setSelectedFact(fact)}
                      style={({ pressed }) => pressed && { opacity: 0.6 }}
                    >
                      <LearnedFactRow fact={fact} />
                    </Pressable>
                  </React.Fragment>
                ))}
            </View>
          ))}

          {facts.length === 0 ? (
            <Text style={styles.empty}>Nothing learned yet — start a conversation.</Text>
          ) : null}
        </View>

        <DisclaimerFooter />

        {/* Account */}
        <View style={styles.accountSection}>
          {authSession?.email ? <Text style={styles.accountEmail}>{authSession.email}</Text> : null}
          <Pressable
            style={({ pressed }) => [styles.logoutButton, pressed && { opacity: 0.7 }]}
            onPress={logout}
          >
            <Text style={styles.logoutText}>Sign out</Text>
          </Pressable>
        </View>

        <FactDetailSheet
          fact={selectedFact}
          categoryLabel={
            selectedFact ? (CATEGORY_LABELS[selectedFact.category] ?? selectedFact.category) : ""
          }
          onClose={() => setSelectedFact(null)}
          onForgotten={() => {
            setSelectedFact(null);
            load();
          }}
        />
      </Animated.ScrollView>
      <GlassHeader title="Profile" scrollY={scrollY} />
    </>
  );
}

const styles = StyleSheet.create({
  identity: { alignItems: "center", gap: 10, paddingTop: 4, paddingBottom: 4 },
  bigAvatar: {
    width: 76,
    height: 76,
    borderRadius: 38,
    backgroundColor: colors.allworthNavy,
    alignItems: "center",
    justifyContent: "center",
  },
  bigAvatarText: { fontSize: 28, fontFamily: fonts.sansBold, color: "#FFFFFF", letterSpacing: 0.5 },
  name: { fontSize: 27, fontFamily: fonts.displayMedium, color: colors.allworthNavy },
  meta: { fontSize: 14, fontFamily: fonts.sans, color: colors.inkTertiary },

  advisorCard: { ...card, flexDirection: "row", alignItems: "center", gap: 12, padding: 14 },
  advisorAvatar: {
    width: 46,
    height: 46,
    borderRadius: 23,
    backgroundColor: colors.allworthNavy,
    alignItems: "center",
    justifyContent: "center",
  },
  advisorAvatarText: {
    fontSize: 15,
    fontFamily: fonts.sansBold,
    color: "#FFFFFF",
    letterSpacing: 0.5,
  },
  advisorName: { fontSize: 16, fontFamily: fonts.sansBold, color: colors.inkPrimary },
  advisorTitle: { fontSize: 13, fontFamily: fonts.sans, color: colors.inkSecondary, marginTop: 2 },
  advisorBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: "rgba(62,113,183,0.12)",
    alignItems: "center",
    justifyContent: "center",
  },

  subtitle: { fontSize: 15, fontFamily: fonts.sans, lineHeight: 21, color: colors.inkSecondary },
  factGroup: { gap: 2 },
  factGroupLabel: {
    fontSize: 13,
    fontFamily: fonts.sansBold,
    color: colors.inkSecondary,
    paddingBottom: 2,
    paddingTop: 6,
  },
  empty: {
    fontSize: 15,
    fontFamily: fonts.sans,
    color: colors.inkTertiary,
    textAlign: "center",
    paddingTop: 24,
  },

  accountSection: {
    alignItems: "center",
    paddingVertical: 8,
    gap: 12,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.hairline,
  },
  accountEmail: { fontSize: 13, fontFamily: fonts.sans, color: colors.inkTertiary },
  logoutButton: {
    paddingHorizontal: 24,
    paddingVertical: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.hairline,
  },
  logoutText: { fontFamily: fonts.sansBold, fontSize: 14, color: colors.inkSecondary },
});
