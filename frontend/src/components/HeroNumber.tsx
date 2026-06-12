import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { useCountUp } from "../anim";
import { colors, fonts, usd } from "../theme";
import { SectionHeader } from "./Rows";

interface Props {
  label: string;
  value: number;
  delta?: { text: string; positive: boolean };
}

export function HeroNumber({ label, value, delta }: Props) {
  const displayed = useCountUp(value);

  return (
    <View style={{ gap: 6 }}>
      <SectionHeader>{label}</SectionHeader>
      <Text style={styles.hero}>{usd(displayed)}</Text>
      {delta ? (
        <Text style={[styles.delta, { color: delta.positive ? colors.gain : colors.loss }]}>
          {delta.text}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  // Large stats render in Playfair Display with tabular lining figures (brand deck p.6)
  hero: {
    fontSize: 48,
    fontFamily: fonts.displayMedium,
    color: colors.inkPrimary,
    fontVariant: ["tabular-nums"],
  },
  delta: { fontSize: 15, fontFamily: fonts.sansBold, fontVariant: ["tabular-nums"] },
});
