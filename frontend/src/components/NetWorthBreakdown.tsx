import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import React, { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useApp } from "../state";
import { card, colors, fonts, usd } from "../theme";
import { HairlineDivider } from "./Rows";

export function BreakdownCard({
  allworthTotal,
  heldAwayTotal,
  liabilitiesTotal,
}: {
  allworthTotal: number;
  heldAwayTotal: number;
  liabilitiesTotal: number;
}) {
  return (
    <View style={styles.card}>
      <View style={styles.segmentBar}>
        <View style={{ flex: allworthTotal, backgroundColor: colors.allworthNavy }} />
        <View style={{ flex: heldAwayTotal, backgroundColor: colors.allworthAccent }} />
      </View>
      <BreakdownRow dot={colors.allworthNavy} label="Managed by Allworth" value={allworthTotal} />
      <HairlineDivider />
      <BreakdownRow
        dot={colors.allworthAccent}
        label="Held away"
        sublabel="Not yet part of your Allworth plan"
        value={heldAwayTotal}
      />
      <HairlineDivider />
      <BreakdownRow label="Liabilities" value={liabilitiesTotal} negative />
    </View>
  );
}

function BreakdownRow({
  dot,
  label,
  sublabel,
  value,
  negative,
}: {
  dot?: string;
  label: string;
  sublabel?: string;
  value: number;
  negative?: boolean;
}) {
  return (
    <View style={styles.row}>
      <View style={[styles.dot, { backgroundColor: dot ?? "transparent" }]} />
      <View style={{ flex: 1 }}>
        <Text style={styles.rowLabel}>{label}</Text>
        {sublabel ? <Text style={styles.rowSublabel}>{sublabel}</Text> : null}
      </View>
      <Text style={[styles.rowValue, negative && { color: colors.loss }]}>{usd(value)}</Text>
    </View>
  );
}

export function CompletePictureCard({ heldAwayTotal }: { heldAwayTotal: number }) {
  const [sent, setSent] = useState(false);
  const { dashboard } = useApp();
  const advisorFirstName = (dashboard?.advisor?.name ?? "Your advisor").split(" ")[0];

  const send = () => {
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    setSent(true);
  };

  return (
    <View style={styles.card}>
      <View style={styles.pictureHeader}>
        <View style={styles.pictureIcon}>
          <Ionicons name="add-circle-outline" size={22} color={colors.allworthAccent} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.pictureTitle}>Complete your picture</Text>
          <Text style={styles.pictureBody}>
            We can see {usd(heldAwayTotal)} held away. Linking the rest helps {advisorFirstName} plan around
            everything you own — taxes, risk, and all.
          </Text>
        </View>
      </View>
      {sent ? (
        <View style={styles.sentRow}>
          <Ionicons name="checkmark-circle" size={17} color={colors.allworthAccent} />
          <Text style={styles.sentText}>
            {advisorFirstName}'s team will reach out to help you connect accounts
          </Text>
        </View>
      ) : (
        <Pressable
          onPress={send}
          style={({ pressed }) => [styles.linkButton, pressed && { opacity: 0.85 }]}
        >
          <Text style={styles.linkButtonText}>Link an account</Text>
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { ...card, padding: 16, gap: 12 },
  segmentBar: {
    flexDirection: "row",
    height: 10,
    borderRadius: 5,
    overflow: "hidden",
    marginBottom: 2,
  },
  row: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 4 },
  dot: { width: 8, height: 8, borderRadius: 4 },
  rowLabel: { fontSize: 15, fontFamily: fonts.sans, color: colors.inkPrimary },
  rowSublabel: { fontSize: 12, fontFamily: fonts.sans, color: colors.inkTertiary, marginTop: 1 },
  rowValue: {
    fontSize: 15,
    fontFamily: fonts.sansBold,
    color: colors.inkPrimary,
    fontVariant: ["tabular-nums"],
  },
  pictureHeader: { flexDirection: "row", gap: 12, alignItems: "flex-start" },
  pictureIcon: { width: 28, paddingTop: 1 },
  pictureTitle: { fontSize: 17, fontFamily: fonts.sansBold, color: colors.inkPrimary },
  pictureBody: {
    fontSize: 14,
    fontFamily: fonts.sans,
    color: colors.inkSecondary,
    lineHeight: 20,
    marginTop: 4,
  },
  linkButton: {
    backgroundColor: colors.allworthAccent,
    paddingVertical: 10,
    borderRadius: 10,
    alignItems: "center",
  },
  linkButtonText: { color: "#fff", fontSize: 15, fontFamily: fonts.sansBold },
  sentRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  sentText: { flex: 1, fontSize: 14, fontFamily: fonts.sans, color: colors.allworthAccent },
});
