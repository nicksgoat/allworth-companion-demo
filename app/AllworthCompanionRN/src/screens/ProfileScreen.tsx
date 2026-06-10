import React, { useCallback, useEffect, useState } from "react";
import { RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { DisclaimerFooter, HairlineDivider, LearnedFactRow, SectionHeader } from "../components/Rows";
import { useApp } from "../state";
import { colors } from "../theme";
import type { LearnedFact } from "../types";

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
  const insets = useSafeAreaInsets();
  const [facts, setFacts] = useState<LearnedFact[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      setFacts((await app.api.profile(app.clientId)).facts);
    } catch {}
  }, [app.api, app.clientId]);

  useEffect(() => {
    load();
  }, [load]);

  const refresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const categories = facts.reduce<string[]>((seen, f) => (seen.includes(f.category) ? seen : [...seen, f.category]), []);

  return (
    <ScrollView
      style={{ backgroundColor: colors.surfacePrimary }}
      contentContainerStyle={{ padding: 20, paddingTop: insets.top + 8, gap: 24 }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
    >
      <View style={{ gap: 6 }}>
        <Text style={styles.title}>What I've learned</Text>
        <Text style={styles.subtitle}>
          Every fact has a source, a timestamp, and an audit trail. Nothing here came from anywhere but you.
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
              <React.Fragment key={fact.fact}>
                {i > 0 ? <HairlineDivider /> : null}
                <LearnedFactRow fact={fact} />
              </React.Fragment>
            ))}
        </View>
      ))}

      {facts.length === 0 ? <Text style={styles.empty}>Nothing learned yet — start a conversation.</Text> : null}

      <View style={{ paddingVertical: 8 }}>
        <DisclaimerFooter />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  title: { fontSize: 28, fontWeight: "600", color: colors.inkPrimary },
  subtitle: { fontSize: 15, lineHeight: 21, color: colors.inkSecondary },
  empty: { fontSize: 15, color: colors.inkTertiary, textAlign: "center", paddingTop: 40 },
});
