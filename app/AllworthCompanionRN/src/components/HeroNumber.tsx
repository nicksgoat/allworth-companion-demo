import React, { useEffect, useRef, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { colors, usd } from "../theme";
import { SectionHeader } from "./Rows";

interface Props {
  label: string;
  value: number;
  delta?: { text: string; positive: boolean };
}

export function HeroNumber({ label, value, delta }: Props) {
  const [displayed, setDisplayed] = useState(Math.round(value * 0.97));
  const raf = useRef<number>(0);

  useEffect(() => {
    const from = Math.round(value * 0.97);
    const start = Date.now();
    const duration = 550;
    setDisplayed(from);
    const tick = () => {
      const t = Math.min(1, (Date.now() - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplayed(Math.round(from + (value - from) * eased));
      if (t < 1) raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [value]);

  return (
    <View style={{ gap: 6 }}>
      <SectionHeader>{label}</SectionHeader>
      <Text style={styles.hero}>{usd(displayed)}</Text>
      {delta ? (
        <Text style={[styles.delta, { color: delta.positive ? colors.gainGreen : colors.lossRed }]}>
          {delta.text}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  hero: {
    fontSize: 48,
    fontWeight: "600",
    color: colors.inkPrimary,
    fontVariant: ["tabular-nums"],
  },
  delta: { fontSize: 15, fontWeight: "500", fontVariant: ["tabular-nums"] },
});
