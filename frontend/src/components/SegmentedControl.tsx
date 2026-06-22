import * as Haptics from "expo-haptics";
import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { colors, fonts, shadowSoft } from "../theme";

export function SegmentedControl({
  options,
  selected,
  onSelect,
}: {
  options: string[];
  selected: string;
  onSelect: (o: string) => void;
}) {
  return (
    <View style={styles.track}>
      {options.map((option) => {
        const active = option === selected;
        return (
          <Pressable
            key={option}
            onPress={() => {
              if (!active) Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
              onSelect(option);
            }}
            style={[styles.segment, active && styles.segmentActive]}
          >
            <Text style={[styles.label, active && styles.labelActive]}>{option}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  track: {
    flexDirection: "row",
    backgroundColor: "rgba(0,0,0,0.06)",
    borderRadius: 10,
    padding: 2,
  },
  segment: { flex: 1, alignItems: "center", paddingVertical: 7, borderRadius: 8 },
  segmentActive: {
    backgroundColor: colors.surfaceCard,
    ...shadowSoft,
  },
  label: { fontSize: 13, fontFamily: fonts.sansBold, color: colors.inkSecondary },
  labelActive: { color: colors.inkPrimary },
});
