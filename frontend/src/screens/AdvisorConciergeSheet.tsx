import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import React, { useState } from "react";
import { Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { DisclaimerFooter, SectionHeader } from "../components/Rows";
import { card, colors, fonts, radius, space, text } from "../theme";
import type { Advisor } from "../types";

// Advisor concierge (stakeholder must-have): book a meeting or send a topic
// request without leaving the app. Demo-grade — slots are synthetic and the
// confirmation is local; the point is the one-tap path to the human.
const SLOTS = ["Fri, Jul 10 · 2:00 PM", "Mon, Jul 13 · 10:30 AM", "Tue, Jul 14 · 3:15 PM"];

export function AdvisorConciergeSheet({
  visible,
  advisor,
  onClose,
}: {
  visible: boolean;
  advisor: Advisor | null;
  onClose: () => void;
}) {
  const [slot, setSlot] = useState<string | null>(null);
  const [topic, setTopic] = useState("");
  const [booked, setBooked] = useState<string | null>(null);
  const [requested, setRequested] = useState(false);

  const close = () => {
    setSlot(null);
    setTopic("");
    setBooked(null);
    setRequested(false);
    onClose();
  };

  const confirmBooking = () => {
    if (!slot) return;
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    setBooked(slot);
  };

  const sendRequest = () => {
    if (!topic.trim()) return;
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    setRequested(true);
  };

  const firstName = advisor?.name?.split(" ")[0] ?? "your advisor";

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={close}>
      <ScrollView
        style={{ backgroundColor: colors.surfacePrimary }}
        contentContainerStyle={{ padding: space[5], gap: space[5], paddingBottom: space[8] }}
        keyboardDismissMode="interactive"
      >
        <View style={styles.headerRow}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>{advisor?.avatarInitials ?? "NM"}</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.advisorName}>{advisor?.name ?? "Your advisor"}</Text>
            <Text style={styles.advisorTitle}>{advisor?.title ?? "Financial Advisor"}</Text>
          </View>
          <Pressable onPress={close} hitSlop={8} style={styles.closeBtn}>
            <Ionicons name="close" size={20} color={colors.inkSecondary} />
          </Pressable>
        </View>

        <View style={{ gap: space[3] }}>
          <SectionHeader>Book a meeting</SectionHeader>
          {booked ? (
            <View style={styles.confirmCard}>
              <Ionicons name="checkmark-circle" size={22} color={colors.gain} />
              <Text style={styles.confirmText}>
                You're on {firstName}'s calendar for {booked}. A confirmation is on its way.
              </Text>
            </View>
          ) : (
            <View style={{ gap: space[2] }}>
              {SLOTS.map((s) => {
                const active = slot === s;
                return (
                  <Pressable
                    key={s}
                    onPress={() => {
                      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
                      setSlot(s);
                    }}
                    style={[styles.slot, active && styles.slotActive]}
                  >
                    <Ionicons
                      name={active ? "radio-button-on" : "radio-button-off"}
                      size={18}
                      color={active ? colors.allworthAccent : colors.inkTertiary}
                    />
                    <Text style={[styles.slotText, active && styles.slotTextActive]}>{s}</Text>
                  </Pressable>
                );
              })}
              <Pressable
                onPress={confirmBooking}
                disabled={!slot}
                style={[styles.primaryBtn, !slot && { opacity: 0.4 }]}
              >
                <Text style={styles.primaryBtnText}>Confirm time</Text>
              </Pressable>
            </View>
          )}
        </View>

        <View style={{ gap: space[3] }}>
          <SectionHeader>Request a topic</SectionHeader>
          {requested ? (
            <View style={styles.confirmCard}>
              <Ionicons name="checkmark-circle" size={22} color={colors.gain} />
              <Text style={styles.confirmText}>
                Sent. {firstName} will come prepared to your next conversation.
              </Text>
            </View>
          ) : (
            <View style={{ gap: space[2] }}>
              <TextInput
                style={styles.topicInput}
                placeholder={`What should ${firstName} look into?`}
                placeholderTextColor={colors.inkTertiary}
                value={topic}
                onChangeText={setTopic}
                multiline
              />
              <Pressable
                onPress={sendRequest}
                disabled={!topic.trim()}
                style={[styles.primaryBtn, !topic.trim() && { opacity: 0.4 }]}
              >
                <Text style={styles.primaryBtnText}>Send to {firstName}</Text>
              </Pressable>
            </View>
          )}
        </View>

        <DisclaimerFooter />
      </ScrollView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  headerRow: { flexDirection: "row", alignItems: "center", gap: space[3], paddingTop: space[2] },
  avatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.allworthNavy,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarText: { fontSize: 15, fontFamily: fonts.sansBold, color: "#FFFFFF" },
  advisorName: { ...text.heading },
  advisorTitle: { ...text.bodySm },
  closeBtn: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.inkFaint,
    alignItems: "center",
    justifyContent: "center",
  },
  slot: {
    ...card,
    flexDirection: "row",
    alignItems: "center",
    gap: space[3],
    paddingHorizontal: space[4],
    paddingVertical: space[3],
  },
  slotActive: { borderColor: colors.allworthAccent },
  slotText: { ...text.body },
  slotTextActive: { fontFamily: fonts.sansBold },
  primaryBtn: {
    backgroundColor: colors.allworthNavy,
    borderRadius: radius.chip,
    alignItems: "center",
    paddingVertical: space[3],
    marginTop: space[1],
  },
  primaryBtnText: { fontSize: 15, fontFamily: fonts.sansBold, color: "#FFFFFF" },
  confirmCard: {
    ...card,
    flexDirection: "row",
    alignItems: "center",
    gap: space[3],
    padding: space[4],
  },
  confirmText: { ...text.body, flex: 1, lineHeight: 21 },
  topicInput: {
    ...card,
    ...text.body,
    minHeight: 84,
    padding: space[4],
    textAlignVertical: "top",
  },
});
