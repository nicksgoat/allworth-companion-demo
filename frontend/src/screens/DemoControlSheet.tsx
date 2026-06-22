import { Ionicons } from "@expo/vector-icons";
import React, { useState } from "react";
import {
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { Mode, useApp } from "../state";
import { card, colors, fonts, shadowSoft } from "../theme";
import { SectionHeader } from "../components/Rows";

const MODES: { value: Mode; label: string }[] = [
  { value: "client", label: "Client" },
  { value: "advisor", label: "Advisor" },
  { value: "vision", label: "Vision" },
];

const SESSIONS = [
  { value: "monday", label: "Monday (first chat)" },
  { value: "wednesday", label: "Wednesday (memory)" },
];

// Hidden demo control sheet — opened by triple-tapping the Allworth wordmark.
export function DemoControlSheet() {
  const app = useApp();
  const [resetDone, setResetDone] = useState(false);

  const close = () => app.setShowDemoControls(false);

  return (
    <Modal
      visible={app.showDemoControls}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={close}
    >
      <View style={styles.root}>
        <View style={styles.header}>
          <Text style={styles.title}>Demo controls</Text>
          <Pressable onPress={close} hitSlop={8}>
            <Text style={styles.done}>Done</Text>
          </Pressable>
        </View>
        <ScrollView contentContainerStyle={{ padding: 20, gap: 24 }}>
          <Section header="View">
            <Segmented options={MODES} value={app.mode} onChange={(m) => app.setMode(m as Mode)} />
          </Section>
          <Section header="Session">
            <Segmented options={SESSIONS} value={app.session} onChange={app.setSession} />
          </Section>
          <Section header="Backend">
            <TextInput
              style={styles.hostInput}
              value={app.backendHost}
              onChangeText={app.setBackendHost}
              autoCapitalize="none"
              autoCorrect={false}
              placeholder="Host"
            />
          </Section>
          <Section footer="Clears conversation state and re-seeds Maya's Monday profile.">
            <Pressable
              onPress={async () => {
                await app.resetDemo();
                setResetDone(true);
              }}
              style={({ pressed }) => [styles.resetButton, pressed && { opacity: 0.8 }]}
            >
              <Text style={styles.resetText}>Reset demo</Text>
              {resetDone ? (
                <Ionicons name="checkmark-circle" size={18} color={colors.gain} />
              ) : null}
            </Pressable>
          </Section>
        </ScrollView>
      </View>
    </Modal>
  );
}

function Section({
  header,
  footer,
  children,
}: {
  header?: string;
  footer?: string;
  children: React.ReactNode;
}) {
  return (
    <View style={{ gap: 8 }}>
      {header ? <SectionHeader>{header}</SectionHeader> : null}
      {children}
      {footer ? <Text style={styles.footerText}>{footer}</Text> : null}
    </View>
  );
}

function Segmented({
  options,
  value,
  onChange,
}: {
  options: { value: string; label: string }[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <View style={styles.segmented}>
      {options.map((opt) => (
        <Pressable
          key={opt.value}
          onPress={() => onChange(opt.value)}
          style={[styles.segment, value === opt.value && styles.segmentActive]}
        >
          <Text
            style={[styles.segmentText, value === opt.value && styles.segmentTextActive]}
            numberOfLines={1}
          >
            {opt.label}
          </Text>
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surfacePrimary },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 20,
    paddingTop: 18,
  },
  title: { fontSize: 17, fontFamily: fonts.sansBold, color: colors.inkPrimary },
  done: { fontSize: 17, fontFamily: fonts.sansBold, color: colors.allworthAccent },
  segmented: {
    flexDirection: "row",
    backgroundColor: colors.inkFaint,
    borderRadius: 9,
    padding: 2,
  },
  segment: { flex: 1, paddingVertical: 7, borderRadius: 7, alignItems: "center" },
  segmentActive: {
    backgroundColor: "#fff",
    ...shadowSoft,
  },
  segmentText: { fontSize: 13, fontFamily: fonts.sans, color: colors.inkSecondary },
  segmentTextActive: { color: colors.inkPrimary, fontFamily: fonts.sansBold },
  hostInput: {
    ...card,
    fontSize: 17,
    fontFamily: fonts.sans,
    color: colors.inkPrimary,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  resetButton: {
    ...card,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 13,
  },
  resetText: { fontSize: 17, fontFamily: fonts.sans, color: colors.loss },
  footerText: { fontSize: 13, fontFamily: fonts.sans, color: colors.inkTertiary },
});
