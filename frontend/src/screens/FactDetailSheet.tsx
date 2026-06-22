import { Ionicons } from "@expo/vector-icons";
import React, { useState } from "react";
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { DisclaimerFooter, SectionHeader, SheetHeader } from "../components/Rows";
import { useApp } from "../state";
import { colors, fonts, shortDate } from "../theme";
import type { LearnedFact } from "../types";

// Governed memory (docs/ALLWORTH_AI_APP_CANONICAL.md): every fact answers
// "Why do you know this?" and supports "Forget this detail".
export function FactDetailSheet({
  fact,
  categoryLabel,
  onClose,
  onForgotten,
}: {
  fact: LearnedFact | null;
  categoryLabel: string;
  onClose: () => void;
  onForgotten: () => void;
}) {
  return (
    <Modal
      visible={fact != null}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={onClose}
    >
      {fact ? (
        <FactDetailContent
          fact={fact}
          categoryLabel={categoryLabel}
          onClose={onClose}
          onForgotten={onForgotten}
        />
      ) : null}
    </Modal>
  );
}

function FactDetailContent({
  fact,
  categoryLabel,
  onClose,
  onForgotten,
}: {
  fact: LearnedFact;
  categoryLabel: string;
  onClose: () => void;
  onForgotten: () => void;
}) {
  const app = useApp();
  const [forgetting, setForgetting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const forget = async () => {
    setForgetting(true);
    setError(null);
    try {
      await app.api.forgetFact(app.clientId, fact.id);
      onForgotten();
    } catch {
      setError("Couldn't reach the backend — try again.");
      setForgetting(false);
    }
  };

  return (
    <ScrollView
      style={{ backgroundColor: colors.surfacePrimary }}
      contentContainerStyle={{ padding: 20, gap: 24 }}
    >
      <View style={{ gap: 6, paddingTop: 24 }}>
        <SheetHeader title={categoryLabel} onClose={onClose} />
        <Text style={styles.fact}>{fact.fact}</Text>
      </View>

      <View style={{ gap: 12 }}>
        <SectionHeader>Why do I know this</SectionHeader>
        {fact.source_quote ? (
          <View style={styles.quoteRow}>
            <View style={styles.quoteBar} />
            <Text style={styles.quoteText}>“{fact.source_quote}”</Text>
          </View>
        ) : null}
        <ProvenanceRow icon="chatbubble-outline" label="Source" value="Your conversation" />
        <ProvenanceRow icon="time-outline" label="Learned" value={shortDate(fact.learned_at)} />
        <ProvenanceRow
          icon="analytics-outline"
          label="Confidence"
          value={`${Math.round(fact.confidence * 100)}%`}
        />
        <ProvenanceRow icon="shield-checkmark-outline" label="Status" value="Active" />
      </View>

      <View style={styles.governanceCard}>
        <Ionicons name="lock-closed-outline" size={18} color={colors.allworthNavy} />
        <Text style={styles.governanceText}>
          You{"'"}re in control. Facts are never shared without your consent, and anything you
          remove stays removed — the removal itself is logged for compliance.
        </Text>
      </View>

      <Pressable
        onPress={forget}
        disabled={forgetting}
        style={({ pressed }) => [styles.forgetButton, pressed && { opacity: 0.85 }]}
      >
        {forgetting ? (
          <ActivityIndicator color={colors.loss} />
        ) : (
          <>
            <Ionicons name="trash-outline" size={18} color={colors.loss} />
            <Text style={styles.forgetText}>Forget this detail</Text>
          </>
        )}
      </Pressable>
      {error ? <Text style={styles.error}>{error}</Text> : null}

      <DisclaimerFooter />
    </ScrollView>
  );
}

function ProvenanceRow({ icon, label, value }: { icon: any; label: string; value: string }) {
  return (
    <View style={styles.provRow}>
      <Ionicons name={icon} size={16} color={colors.inkTertiary} />
      <Text style={styles.provLabel}>{label}</Text>
      <Text style={styles.provValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  fact: { fontSize: 22, fontFamily: fonts.displayMedium, lineHeight: 29, color: colors.inkPrimary },
  quoteRow: { flexDirection: "row", gap: 10 },
  quoteBar: { width: 3, borderRadius: 2, backgroundColor: colors.allworthAccent },
  quoteText: {
    flex: 1,
    fontSize: 15,
    lineHeight: 21,
    fontFamily: fonts.sansItalic,
    color: colors.inkSecondary,
  },
  provRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  provLabel: { fontSize: 14, fontFamily: fonts.sans, color: colors.inkTertiary, width: 86 },
  provValue: { fontSize: 14, fontFamily: fonts.sansBold, color: colors.inkPrimary },
  governanceCard: {
    flexDirection: "row",
    gap: 10,
    alignItems: "flex-start",
    backgroundColor: colors.inkFaint,
    borderRadius: 12,
    padding: 14,
  },
  governanceText: {
    flex: 1,
    fontSize: 13,
    fontFamily: fonts.sans,
    lineHeight: 19,
    color: colors.inkSecondary,
  },
  forgetButton: {
    flexDirection: "row",
    gap: 8,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: colors.loss,
    borderRadius: 12,
    paddingVertical: 14,
  },
  forgetText: { color: colors.loss, fontSize: 17, fontFamily: fonts.sansBold },
  error: { fontSize: 13, fontFamily: fonts.sans, color: colors.loss, textAlign: "center" },
});
