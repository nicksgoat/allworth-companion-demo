import { Ionicons } from "@expo/vector-icons";
import React from "react";
import { Modal, ScrollView, StyleSheet, Text, View } from "react-native";
import { DisclaimerFooter, SectionHeader, SheetHeader } from "../components/Rows";
import { colors, fonts, shortDate } from "../theme";
import type { MeetingNote } from "../types";

// Read-only detail for a seeded meeting note. Mirrors FactDetailSheet's
// modal-from-state pattern (slide-up pageSheet with a visible close).
export function MeetingNoteDetailSheet({
  note,
  onClose,
}: {
  note: MeetingNote | null;
  onClose: () => void;
}) {
  return (
    <Modal
      visible={note != null}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={onClose}
    >
      {note ? <MeetingNoteDetailContent note={note} onClose={onClose} /> : null}
    </Modal>
  );
}

function MeetingNoteDetailContent({ note, onClose }: { note: MeetingNote; onClose: () => void }) {
  return (
    <ScrollView
      style={{ backgroundColor: colors.surfacePrimary }}
      contentContainerStyle={{ padding: 20, gap: 24, paddingTop: 0 }}
    >
      <SheetHeader title="Meeting note" onClose={onClose} />
      <View style={{ gap: 8 }}>
        <Text style={styles.title}>{note.title}</Text>
        <Text style={styles.meta}>
          {shortDate(note.date)} · with {note.advisor}
        </Text>
      </View>

      <Text style={styles.summary}>{note.summary}</Text>

      {note.attendees && note.attendees.length > 0 ? (
        <View style={{ gap: 12 }}>
          <SectionHeader>Who was there</SectionHeader>
          {note.attendees.map((person) => (
            <View key={person} style={styles.attendeeRow}>
              <Ionicons name="person-circle-outline" size={20} color={colors.inkTertiary} />
              <Text style={styles.attendeeName}>{person}</Text>
            </View>
          ))}
        </View>
      ) : null}

      <DisclaimerFooter />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  title: {
    fontSize: 24,
    fontFamily: fonts.displayMedium,
    lineHeight: 30,
    color: colors.allworthNavy,
  },
  meta: { fontSize: 14, fontFamily: fonts.sans, color: colors.inkTertiary },
  summary: { fontSize: 17, fontFamily: fonts.sans, lineHeight: 25, color: colors.inkPrimary },
  attendeeRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  attendeeName: { fontSize: 16, fontFamily: fonts.sans, color: colors.inkPrimary },
});
