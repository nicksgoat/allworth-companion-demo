import { Ionicons } from "@expo/vector-icons";
import React, { useEffect, useState } from "react";
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { AdvisorHandoffCard } from "../components/AdvisorHandoffCard";
import { iconFor, leadingPct, severityFor } from "../components/NudgeCard";
import { DisclaimerFooter, SectionHeader } from "../components/Rows";
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

  const sev = severityFor(nudge.severity);
  const pct = leadingPct(nudge.headline);
  const tint = sev.color + "1A";

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
      contentContainerStyle={{ paddingBottom: 32 }}
    >
      {/* Severity-tinted hero header */}
      <View style={[styles.hero, { backgroundColor: tint }]}>
        <View style={styles.heroTop}>
          <View style={[styles.iconChip, { backgroundColor: sev.color }]}>
            <Ionicons name={iconFor(nudge.type)} size={20} color="#FFFFFF" />
          </View>
          <Pressable onPress={onClose} hitSlop={10} style={styles.closeBtn}>
            <Ionicons name="close" size={20} color={colors.inkSecondary} />
          </Pressable>
        </View>
        <View style={[styles.tag, { backgroundColor: "rgba(255,255,255,0.6)" }]}>
          <Text style={[styles.tagText, { color: sev.color }]}>{sev.label}</Text>
        </View>
        <Text style={[styles.heroMetric, { color: sev.color }]}>{nudge.headline}</Text>
        <Text style={styles.heroTitle}>{nudge.title}</Text>
      </View>

      <View style={styles.bodyWrap}>
        <Text style={styles.body}>{nudge.body}</Text>

        {nudge.type === "spending" && spending ? <SpendingBars s={spending} /> : null}
        {nudge.type === "concentration" && pct != null ? (
          <ConcentrationBar pct={pct} color={sev.color} headline={nudge.headline} />
        ) : null}

        <Pressable
          onPress={askAssistant}
          style={({ pressed }) => [styles.cta, pressed && { opacity: 0.9 }]}
        >
          <Ionicons name="chatbubbles-outline" size={18} color="#fff" />
          <Text style={styles.ctaText}>{nudge.cta}</Text>
        </Pressable>

        <AdvisorHandoffCard />
        <DisclaimerFooter />
      </View>
    </ScrollView>
  );
}

function ConcentrationBar({
  pct,
  color,
  headline,
}: {
  pct: number;
  color: string;
  headline: string;
}) {
  return (
    <View style={{ gap: 10 }}>
      <SectionHeader>Share of the account</SectionHeader>
      <View style={styles.concTrack}>
        <View style={[styles.concFill, { width: `${Math.min(100, pct)}%`, backgroundColor: color }]} />
      </View>
      <View style={styles.concLegend}>
        <Text style={[styles.concPct, { color }]}>{headline}</Text>
        <Text style={styles.concRest}>{Math.max(0, 100 - Math.round(pct))}% everything else</Text>
      </View>
    </View>
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
  hero: {
    paddingTop: 22,
    paddingHorizontal: 20,
    paddingBottom: 22,
    borderBottomLeftRadius: 24,
    borderBottomRightRadius: 24,
    gap: 10,
  },
  heroTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  iconChip: { width: 42, height: 42, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  closeBtn: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: "rgba(255,255,255,0.7)",
    alignItems: "center",
    justifyContent: "center",
  },
  tag: { alignSelf: "flex-start", paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999 },
  tagText: { fontSize: 12, fontFamily: fonts.sansBold, letterSpacing: 0.3 },
  // Large stats render in Playfair Display with tabular lining figures (brand deck p.6)
  heroMetric: {
    fontSize: 40,
    fontFamily: fonts.displayMedium,
    fontVariant: ["tabular-nums"],
    marginTop: 2,
  },
  heroTitle: { fontSize: 18, fontFamily: fonts.sans, color: colors.inkPrimary, lineHeight: 24 },

  bodyWrap: { padding: 20, gap: 20 },
  body: { fontSize: 17, fontFamily: fonts.sans, lineHeight: 24, color: colors.inkPrimary },

  cta: {
    flexDirection: "row",
    gap: 8,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.allworthAccent,
    borderRadius: 12,
    paddingVertical: 15,
  },
  ctaText: { color: "#fff", fontSize: 17, fontFamily: fonts.sansBold },

  concTrack: {
    height: 14,
    borderRadius: 7,
    backgroundColor: colors.inkFaint,
    overflow: "hidden",
  },
  concFill: { position: "absolute", left: 0, top: 0, bottom: 0, borderRadius: 7 },
  concLegend: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  concPct: { fontSize: 15, fontFamily: fonts.sansBold, fontVariant: ["tabular-nums"] },
  concRest: { fontSize: 14, fontFamily: fonts.sans, color: colors.inkTertiary },

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
