import { Ionicons } from "@expo/vector-icons";
import { useNavigation } from "@react-navigation/native";
import { createNativeStackNavigator, NativeStackScreenProps } from "@react-navigation/native-stack";
import React, { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { HeroNumber } from "../components/HeroNumber";
import {
  AccountRow,
  DisclaimerFooter,
  HairlineDivider,
  LearnedFactRow,
  SectionHeader,
} from "../components/Rows";
import { AllworthWordmark } from "../components/Wordmark";
import { useApp } from "../state";
import { card, colors, usd } from "../theme";
import type { AdvisorBrief, BookResponse, Household } from "../types";

type AdvisorStackParams = {
  Book: undefined;
  ClientDetail: { household: Household };
};

const Stack = createNativeStackNavigator<AdvisorStackParams>();

export function AdvisorNavigator() {
  return (
    <Stack.Navigator screenOptions={{ headerTintColor: colors.allworthNavy }}>
      <Stack.Screen name="Book" component={BookScreen} options={{ headerShown: false }} />
      <Stack.Screen
        name="ClientDetail"
        component={ClientDetailScreen}
        options={({ route }) => ({ title: route.params.household.name, headerBackTitle: "Book" })}
      />
    </Stack.Navigator>
  );
}

function BookScreen() {
  const app = useApp();
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<any>();
  const [book, setBook] = useState<BookResponse | null>(null);
  const autoPushed = useRef(false);

  useEffect(() => {
    app.api
      .book("dana")
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
    <ScrollView
      style={{ backgroundColor: colors.surfacePrimary }}
      contentContainerStyle={{ padding: 20, paddingTop: insets.top + 8, gap: 20 }}
    >
      <View style={styles.headerRow}>
        <View style={{ gap: 2 }}>
          <Text style={styles.title}>Your book</Text>
          {book ? (
            <Text style={styles.subtitle}>
              {book.advisor.name} · {book.advisor.title}
            </Text>
          ) : null}
        </View>
        <AllworthWordmark />
      </View>

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
  );
}

function HouseholdRow({ household, onPress }: { household: Household; onPress: () => void }) {
  const initials = household.name
    .split(" ")
    .map((w) => w[0])
    .slice(0, 2)
    .join("");
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
        <Text style={[styles.householdName, highlight && { fontWeight: "600" }]}>
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
    app.api
      .brief("dana", household.clientId)
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

          {brief.openNudges.length > 0 ? (
            <View style={{ gap: 8 }}>
              <SectionHeader>Open nudges</SectionHeader>
              {brief.openNudges.map((nudge) => (
                <View key={nudge.id} style={styles.nudgeRow}>
                  <View style={styles.nudgeDot} />
                  <Text style={styles.nudgeTitle}>{nudge.title}</Text>
                  <Text style={styles.nudgeHeadline}>{nudge.headline}</Text>
                </View>
              ))}
            </View>
          ) : null}

          {brief.profile.length > 0 ? (
            <View>
              <View style={{ paddingBottom: 4 }}>
                <SectionHeader>What the assistant has learned</SectionHeader>
              </View>
              {brief.profile.slice(0, 4).map((fact, i) => (
                <React.Fragment key={fact.fact}>
                  {i > 0 ? <HairlineDivider /> : null}
                  <LearnedFactRow fact={fact} />
                </React.Fragment>
              ))}
            </View>
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

const styles = StyleSheet.create({
  headerRow: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between" },
  title: { fontSize: 28, fontWeight: "600", color: colors.inkPrimary },
  subtitle: { fontSize: 13, color: colors.inkSecondary },
  householdRow: { flexDirection: "row", alignItems: "center", gap: 12, paddingVertical: 12 },
  householdAvatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
  },
  householdInitials: { fontSize: 14, fontWeight: "600" },
  householdName: { fontSize: 17, color: colors.inkPrimary },
  householdManaged: { fontSize: 13, color: colors.inkTertiary },
  householdHeldAway: { fontSize: 13, fontWeight: "500", color: colors.allworthAccent },
  nudgeBadge: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: colors.attention,
    alignItems: "center",
    justifyContent: "center",
  },
  nudgeBadgeText: { color: "#fff", fontSize: 13, fontWeight: "600" },
  managedCaption: { fontSize: 15, color: colors.inkSecondary, fontVariant: ["tabular-nums"] },
  briefCard: { ...card, padding: 16, gap: 10 },
  briefHeader: { flexDirection: "row", alignItems: "center", gap: 6 },
  briefText: { fontSize: 15, lineHeight: 22, color: colors.inkPrimary },
  nudgeRow: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 6 },
  nudgeDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.attention },
  nudgeTitle: { flex: 1, fontSize: 15, color: colors.inkPrimary },
  nudgeHeadline: {
    fontSize: 13,
    fontWeight: "600",
    color: colors.attention,
    fontVariant: ["tabular-nums"],
  },
});
