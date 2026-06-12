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
import { colors, fonts } from "../theme";
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
        <View style={{ gap: 6 }}>
          <Text style={styles.title}>What I{"'"}ve learned</Text>
          <Text style={styles.subtitle}>
            Every fact has a source, a timestamp, and an audit trail. Nothing here came from
            anywhere but you. Tap any fact to see why I know it — or to remove it.
          </Text>
        </View>

        {categories.map((category) => (
          <View key={category}>
            <View style={{ paddingBottom: 4 }}>
              <SectionHeader>{CATEGORY_LABELS[category] ?? category}</SectionHeader>
            </View>
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

        <View style={{ paddingVertical: 8 }}>
          <DisclaimerFooter />
        </View>

        {/* Signed-in user info + logout */}
        <View style={styles.accountSection}>
          {authSession?.email && (
            <Text style={styles.accountEmail}>{authSession.email}</Text>
          )}
          <Pressable style={styles.logoutButton} onPress={logout}>
            <Text style={styles.logoutText}>Sign Out</Text>
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
      <GlassHeader title="What I've learned" scrollY={scrollY} />
    </>
  );
}

const styles = StyleSheet.create({
  title: { fontSize: 28, fontFamily: fonts.display, color: colors.inkPrimary },
  subtitle: { fontSize: 15, fontFamily: fonts.sans, lineHeight: 21, color: colors.inkSecondary },
  empty: {
    fontSize: 15,
    fontFamily: fonts.sans,
    color: colors.inkTertiary,
    textAlign: "center",
    paddingTop: 40,
  },
  accountSection: {
    alignItems: "center",
    paddingVertical: 16,
    gap: 12,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.hairline,
  },
  accountEmail: {
    fontSize: 13,
    fontFamily: fonts.sans,
    color: colors.inkTertiary,
  },
  logoutButton: {
    paddingHorizontal: 24,
    paddingVertical: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.hairline,
  },
  logoutText: {
    fontFamily: fonts.sansBold,
    fontSize: 14,
    color: colors.loss,
  },
});
