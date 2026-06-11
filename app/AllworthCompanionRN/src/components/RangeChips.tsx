import * as Haptics from "expo-haptics";
import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { colors, fonts } from "../theme";

export function RangeChips({
  options,
  selected,
  onSelect,
}: {
  options: string[];
  selected: string;
  onSelect: (o: string) => void;
}) {
  return (
    <View style={styles.row}>
      {options.map((option) => {
        const active = option === selected;
        return (
          <Pressable
            key={option}
            onPress={() => {
              if (!active) Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
              onSelect(option);
            }}
            style={({ pressed }) => [
              styles.chip,
              { backgroundColor: active ? colors.allworthNavy : colors.inkFaint },
              pressed && { opacity: 0.85 },
            ]}
          >
            <Text style={[styles.label, { color: active ? "#fff" : colors.inkSecondary }]}>
              {option}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", gap: 8 },
  chip: { paddingHorizontal: 16, paddingVertical: 7, borderRadius: 16 },
  label: { fontSize: 13, fontFamily: fonts.sansBold },
});
