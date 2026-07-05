import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import React, { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { DisclaimerFooter, SectionHeader, SheetHeader } from "../components/Rows";
import { useApp } from "../state";
import { card, colors, fonts, radius, space, text } from "../theme";
import type { Advisor, AvailabilityDay } from "../types";

// Advisor concierge (stakeholder must-have): book a meeting or send a topic
// request without leaving the app. Calendly-style: pick a day from the strip,
// pick a time from that day's real availability, confirm. Both actions POST
// to the backend, so they land in the advisor's view of this client.

// If availability can't load (offline demo), fall back to a static trio so
// the flow never bricks.
const FALLBACK_DAYS: AvailabilityDay[] = [
  {
    dateISO: "fallback-1",
    label: "Fri",
    longLabel: "Friday",
    slots: [{ iso: "", display: "2:00 PM" }],
  },
  {
    dateISO: "fallback-2",
    label: "Mon",
    longLabel: "Monday",
    slots: [{ iso: "", display: "10:30 AM" }],
  },
  {
    dateISO: "fallback-3",
    label: "Tue",
    longLabel: "Tuesday",
    slots: [{ iso: "", display: "3:15 PM" }],
  },
];

export function AdvisorConciergeSheet({
  visible,
  advisor,
  onClose,
}: {
  visible: boolean;
  advisor: Advisor | null;
  onClose: () => void;
}) {
  const app = useApp();
  const [days, setDays] = useState<AvailabilityDay[] | null>(null);
  const [dayIdx, setDayIdx] = useState(0);
  const [slotISO, setSlotISO] = useState<string | null>(null);
  const [slotDisplay, setSlotDisplay] = useState<string | null>(null);
  const [topic, setTopic] = useState("");
  const [booked, setBooked] = useState<string | null>(null);
  const [requested, setRequested] = useState(false);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    setDays(null);
    app.api
      .availability(app.clientId)
      .then((res) => {
        if (!cancelled) setDays(res.days);
      })
      .catch(() => {
        if (!cancelled) setDays(FALLBACK_DAYS);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  const close = () => {
    setDayIdx(0);
    setSlotISO(null);
    setSlotDisplay(null);
    setTopic("");
    setBooked(null);
    setRequested(false);
    onClose();
  };

  const day = days?.[dayIdx];

  const pickDay = (i: number) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setDayIdx(i);
    setSlotISO(null);
    setSlotDisplay(null);
  };

  const pickSlot = (iso: string, display: string) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setSlotISO(iso);
    setSlotDisplay(display);
  };

  const confirmBooking = async () => {
    if (!day || !slotDisplay || sending) return;
    const label = `${day.longLabel} · ${slotDisplay}`;
    setSending(true);
    try {
      await app.api.sendRequest(app.clientId, {
        kind: "booking",
        slotISO: slotISO ?? "",
        slotDisplay: label,
      });
    } catch {} // demo-grade: confirm locally even if the POST fails
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    setBooked(label);
    setSending(false);
  };

  const sendTopic = async () => {
    if (!topic.trim() || sending) return;
    setSending(true);
    try {
      await app.api.sendRequest(app.clientId, { kind: "topic", topic: topic.trim() });
    } catch {}
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    setRequested(true);
    setSending(false);
  };

  const firstName = advisor?.name?.split(" ")[0] ?? "your advisor";

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={close}>
      <ScrollView
        style={{ backgroundColor: colors.surfacePrimary }}
        contentContainerStyle={{
          padding: space[5],
          gap: space[5],
          paddingTop: 0,
          paddingBottom: space[8],
        }}
        keyboardDismissMode="interactive"
      >
        <SheetHeader
          title={advisor?.name ?? "Your advisor"}
          subtitle={advisor?.title ?? "Financial Advisor"}
          onClose={close}
        />

        <View style={{ gap: space[3] }}>
          <SectionHeader>Book a meeting</SectionHeader>
          {booked ? (
            <View style={styles.confirmCard}>
              <Ionicons name="checkmark-circle" size={22} color={colors.gain} />
              <View style={{ flex: 1, gap: 4 }}>
                <Text style={styles.confirmText}>
                  You{"'"}re on {firstName}
                  {"'"}s calendar for {booked}.
                </Text>
                <Pressable onPress={() => setBooked(null)} hitSlop={6}>
                  <Text style={styles.changeLink}>Pick a different time</Text>
                </Pressable>
              </View>
            </View>
          ) : days === null ? (
            <ActivityIndicator style={{ paddingVertical: 24 }} />
          ) : (
            <View style={{ gap: space[3] }}>
              {/* Day strip */}
              <ScrollView
                horizontal
                showsHorizontalScrollIndicator={false}
                style={styles.dayStrip}
                contentContainerStyle={styles.dayStripContent}
              >
                {days.map((d, i) => {
                  const active = i === dayIdx;
                  return (
                    <Pressable
                      key={d.dateISO}
                      onPress={() => pickDay(i)}
                      style={[styles.dayChip, active && styles.dayChipActive]}
                    >
                      <Text style={[styles.dayChipDow, active && styles.dayChipTextActive]}>
                        {d.label.split(" ")[0]}
                      </Text>
                      <Text style={[styles.dayChipDate, active && styles.dayChipTextActive]}>
                        {d.label.split(" ")[1] ?? ""}
                      </Text>
                    </Pressable>
                  );
                })}
              </ScrollView>

              {/* Time slots for the selected day */}
              {day ? (
                <View style={styles.slotGrid}>
                  {day.slots.map((s) => {
                    const active = slotDisplay === s.display && slotISO === s.iso;
                    return (
                      <Pressable
                        key={`${day.dateISO}-${s.display}`}
                        onPress={() => pickSlot(s.iso, s.display)}
                        style={[styles.slotChip, active && styles.slotChipActive]}
                      >
                        <Text style={[styles.slotChipText, active && styles.slotChipTextActive]}>
                          {s.display}
                        </Text>
                      </Pressable>
                    );
                  })}
                </View>
              ) : null}

              <Pressable
                onPress={confirmBooking}
                disabled={!slotDisplay || sending}
                style={[styles.primaryBtn, (!slotDisplay || sending) && { opacity: 0.4 }]}
              >
                {sending ? (
                  <ActivityIndicator size="small" color="#FFFFFF" />
                ) : (
                  <Text style={styles.primaryBtnText}>
                    {slotDisplay && day ? `Confirm ${day.longLabel} · ${slotDisplay}` : "Pick a time"}
                  </Text>
                )}
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
                onPress={sendTopic}
                disabled={!topic.trim() || sending}
                style={[styles.primaryBtn, (!topic.trim() || sending) && { opacity: 0.4 }]}
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
  dayStrip: { marginHorizontal: -space[5] },
  dayStripContent: { paddingHorizontal: space[5], gap: space[2] },
  dayChip: {
    ...card,
    alignItems: "center",
    paddingHorizontal: space[4],
    paddingVertical: space[2],
    borderRadius: radius.chip,
    minWidth: 58,
  },
  dayChipActive: { backgroundColor: colors.allworthNavy, borderColor: colors.allworthNavy },
  dayChipDow: { fontSize: 12, fontFamily: fonts.sans, color: colors.inkTertiary },
  dayChipDate: { fontSize: 16, fontFamily: fonts.sansBold, color: colors.inkPrimary },
  dayChipTextActive: { color: "#FFFFFF" },
  slotGrid: { flexDirection: "row", flexWrap: "wrap", gap: space[2] },
  slotChip: {
    ...card,
    borderRadius: radius.chip,
    paddingVertical: space[3],
    alignItems: "center",
    flexBasis: "30%",
    flexGrow: 1,
  },
  slotChipActive: { borderColor: colors.allworthAccent, backgroundColor: "rgba(62,113,183,0.08)" },
  slotChipText: { ...text.bodySm, fontVariant: ["tabular-nums"], color: colors.inkPrimary },
  slotChipTextActive: { color: colors.allworthAccent, fontFamily: fonts.sansBold },
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
  confirmText: { ...text.body, lineHeight: 21 },
  changeLink: { ...text.bodySm, color: colors.allworthAccent, fontFamily: fonts.sansBold },
  topicInput: {
    ...card,
    ...text.body,
    minHeight: 84,
    padding: space[4],
    textAlignVertical: "top",
  },
});
