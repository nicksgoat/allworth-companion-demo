import React, { useRef } from "react";
import { Pressable, StyleSheet, Text } from "react-native";
import { colors } from "../theme";
import { useApp } from "../state";

// The Allworth wordmark — triple-tap opens the hidden demo control sheet.
export function AllworthWordmark({ light }: { light?: boolean }) {
  const app = useApp();
  const taps = useRef<number[]>([]);

  const onPress = () => {
    const now = Date.now();
    taps.current = [...taps.current.filter((t) => now - t < 600), now];
    if (taps.current.length >= 3) {
      taps.current = [];
      app.setShowDemoControls(true);
    }
  };

  return (
    <Pressable onPress={onPress} hitSlop={8}>
      <Text style={[styles.wordmark, light && { color: "#fff" }]}>ALLWORTH</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  wordmark: { fontSize: 13, fontWeight: "700", letterSpacing: 2.5, color: colors.allworthNavy },
});
