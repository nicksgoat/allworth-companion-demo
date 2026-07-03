import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import React, { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { card, colors, space, text } from "../theme";
import { SectionHeader } from "./Rows";

// The glance rule (DESIGN.md): a screen's key state fits the first viewport;
// detail lives behind a tap. This is the one summary-first container — header
// (+ optional one-line preview) always visible, body collapsed by default.
export function CollapsibleCard({
  icon,
  title,
  preview,
  initiallyExpanded = false,
  children,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  preview?: string;
  initiallyExpanded?: boolean;
  children: React.ReactNode;
}) {
  const [expanded, setExpanded] = useState(initiallyExpanded);

  const toggle = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setExpanded((v) => !v);
  };

  return (
    <View style={styles.card}>
      <Pressable
        onPress={toggle}
        hitSlop={6}
        style={({ pressed }) => [styles.header, pressed && { opacity: 0.6 }]}
      >
        <Ionicons name={icon} size={13} color={colors.allworthAccent} />
        <SectionHeader>{title}</SectionHeader>
        <View style={{ flex: 1 }} />
        <Ionicons
          name={expanded ? "chevron-up" : "chevron-down"}
          size={14}
          color={colors.inkTertiary}
        />
      </Pressable>
      {preview && !expanded ? (
        <Text style={styles.preview} numberOfLines={2}>
          {preview}
        </Text>
      ) : null}
      {expanded ? (
        <View style={{ gap: space[3] }}>
          {preview ? <Text style={styles.preview}>{preview}</Text> : null}
          {children}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { ...card, padding: space[4], gap: space[3] },
  header: { flexDirection: "row", alignItems: "center", gap: space[2] },
  preview: { ...text.body, lineHeight: 22 },
});
