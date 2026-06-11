import { Ionicons } from "@expo/vector-icons";
import React, { useEffect, useState } from "react";
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { AdvisorHandoffCard } from "../components/AdvisorHandoffCard";
import { DisclaimerFooter, SectionHeader, SheetHeader } from "../components/Rows";
import { useApp } from "../state";
import { colors, fonts, monthName, usd } from "../theme";
import type { Nudge, SpendingDetail } from "../types";

export function NudgeDetailSheet({ nudge, onClose }: { nudge: Nudge | null; onClose: () => void }) {
  return (
    <Modal
      visible={nudge != null}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={onClose}
    >
      {nudge ? <NudgeDetailContent nudge={nudge} onClose={onClose} /> : null}
    </Modal>
  );
}

function NudgeDetailContent({ nudge, onClose }: { nudge: Nudge; onClose: () => void }) {
  const app = useApp();
  const [spending, setSpending] = useState<SpendingDetail | null>(null);

  useEffect(() => {
    if (nudge.type === "spending") {
      app.api
        .spending(app.clientId)
        .then(setSpending)
        .catch(() => {});
    }
  }, [nudge]);

  const chatPrompt =
    nudge.type === "spending"
      ? "I know we've been spending more the last few months — what does that actually mean for my plan?"
      : nudge.type === "concentration"
        ? "What are my options for the concentrated position you flagged?"
        : nudge.cta;

  const askAssistant = () => {
    app.setChatPrefill(chatPrompt);
    app.setSelectedTab("chat");
    onClose();
  };

  return (
    <ScrollView
      style={{ backgroundColor: colors.surfacePrimary }}
      contentContainerStyle={{ padding: 20, gap: 20 }}
    >
      <View style={{ gap: 6, paddingTop: 24 }}>
        <SheetHeader title={nudge.title} onClose={onClose} />
        <Text style={styles.headline}>{nudge.headline}</Text>
      </View>

      <Text style={styles.body}>{nudge.body}</Text>

      {nudge.type === "spending" && spending ? <SpendingBars s={spending} /> : null}

      <Pressable
        onPress={askAssistant}
        style={({ pressed }) => [styles.cta, pressed && { opacity: 0.85 }]}
      >
        <Ionicons name="chatbubbles-outline" size={18} color="#fff" />
        <Text style={styles.ctaText}>{nudge.cta}</Text>
      </Pressable>

      <AdvisorHandoffCard />
      <DisclaimerFooter />
    </ScrollView>
  );
}

function SpendingBars({ s }: { s: SpendingDetail }) {
  return (
    <View style={{ gap: 10 }}>
      <SectionHeader>{`Last ${s.months.length} months vs plan`}</SectionHeader>
      {s.months.map((month) => {
        const ratio = Math.min(1, month.total / month.planned / 1.4);
        const over = month.total > month.planned;
        return (
          <View key={month.month} style={styles.barRow}>
            <Text style={styles.barMonth}>{monthName(month.month)}</Text>
            <View style={styles.barTrack}>
              <View
                style={[
                  styles.barFill,
                  {
                    width: `${ratio * 100}%`,
                    backgroundColor: over ? colors.attention : colors.allworthNavy,
                  },
                ]}
              />
            </View>
            <Text style={styles.barValue}>{usd(month.total)}</Text>
          </View>
        );
      })}
      <Text style={styles.planCaption}>
        Plan: {usd(s.plan)}/mo · Recent average: {usd(s.avg3mo)}/mo
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  // Large stats render in Playfair Display with tabular lining figures (brand deck p.6)
  headline: {
    fontSize: 44,
    fontFamily: fonts.displayMedium,
    color: colors.attention,
    fontVariant: ["tabular-nums"],
  },
  body: { fontSize: 17, fontFamily: fonts.sans, lineHeight: 24, color: colors.inkPrimary },
  cta: {
    flexDirection: "row",
    gap: 8,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.allworthAccent,
    borderRadius: 12,
    paddingVertical: 14,
  },
  ctaText: { color: "#fff", fontSize: 17, fontFamily: fonts.sansBold },
  barRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  barMonth: {
    width: 30,
    fontSize: 13,
    fontFamily: fonts.sans,
    color: colors.inkTertiary,
    fontVariant: ["tabular-nums"],
  },
  barTrack: {
    flex: 1,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.inkFaint,
    overflow: "hidden",
  },
  barFill: { height: 8, borderRadius: 4 },
  barValue: {
    width: 64,
    textAlign: "right",
    fontSize: 13,
    fontFamily: fonts.sans,
    color: colors.inkSecondary,
    fontVariant: ["tabular-nums"],
  },
  planCaption: { fontSize: 13, fontFamily: fonts.sans, color: colors.inkTertiary },
});
