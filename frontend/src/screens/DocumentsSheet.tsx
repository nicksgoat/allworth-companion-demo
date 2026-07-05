import { Ionicons } from "@expo/vector-icons";
import React from "react";
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { DisclaimerFooter, SectionHeader } from "../components/Rows";
import { card, colors, fonts, space, text } from "../theme";

// Document vault placeholder (stakeholder "maybe": Avantos-style doc vault).
// Synthetic documents, no viewer — the demo beat is that statements, plans,
// and estate docs live in the same place the conversation does.
const DOCUMENTS: { icon: keyof typeof Ionicons.glyphMap; name: string; meta: string }[] = [
  { icon: "document-text-outline", name: "Financial Plan — 2026 Review", meta: "Updated Jun 10, 2026 · PDF" },
  { icon: "receipt-outline", name: "2025 Tax Return", meta: "Filed Apr 2026 · PDF" },
  { icon: "stats-chart-outline", name: "Q2 2026 Consolidated Statement", meta: "Jun 30, 2026 · PDF" },
  { icon: "shield-checkmark-outline", name: "Estate Plan Summary", meta: "Reviewed Jan 2026 · PDF" },
  { icon: "home-outline", name: "Lake House Goal Worksheet", meta: "Shared by Nicole · May 2026" },
];

export function DocumentsSheet({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <ScrollView
        style={{ backgroundColor: colors.surfacePrimary }}
        contentContainerStyle={{ padding: space[5], gap: space[4], paddingBottom: space[8] }}
      >
        <View style={styles.headerRow}>
          <Text style={styles.title}>Documents</Text>
          <Pressable onPress={onClose} hitSlop={8} style={styles.closeBtn}>
            <Ionicons name="close" size={20} color={colors.inkSecondary} />
          </Pressable>
        </View>

        <View style={{ gap: space[2] }}>
          <SectionHeader>Your vault</SectionHeader>
          {DOCUMENTS.map((doc) => (
            <View key={doc.name} style={styles.docRow}>
              <View style={styles.docIcon}>
                <Ionicons name={doc.icon} size={18} color={colors.allworthNavy} />
              </View>
              <View style={{ flex: 1, gap: 2 }}>
                <Text style={styles.docName}>{doc.name}</Text>
                <Text style={styles.docMeta}>{doc.meta}</Text>
              </View>
              <Ionicons name="chevron-forward" size={16} color={colors.inkTertiary} />
            </View>
          ))}
        </View>

        <Text style={styles.syncNote}>
          Vault synced with your advisor's records. Ask in chat about any document — the
          assistant knows what's here.
        </Text>

        <DisclaimerFooter />
      </ScrollView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingTop: space[2],
  },
  title: { ...text.title },
  closeBtn: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.inkFaint,
    alignItems: "center",
    justifyContent: "center",
  },
  docRow: {
    ...card,
    flexDirection: "row",
    alignItems: "center",
    gap: space[3],
    paddingHorizontal: space[4],
    paddingVertical: space[3],
  },
  docIcon: {
    width: 36,
    height: 36,
    borderRadius: 10,
    backgroundColor: colors.ice,
    alignItems: "center",
    justifyContent: "center",
  },
  docName: { ...text.body, fontFamily: fonts.sansBold },
  docMeta: { ...text.caption },
  syncNote: { ...text.bodySm, lineHeight: 19 },
});
