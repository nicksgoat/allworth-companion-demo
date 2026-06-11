import React from "react";
import { Animated, Platform, StyleSheet, ViewStyle } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors, fonts } from "../theme";

export const TAB_BAR_HEIGHT = 60;

// Liquid-glass surface: react-native-web passes backdropFilter through to
// CSS; native (no expo-blur installed) falls back to a near-opaque wash.
export const glassStyle: ViewStyle = Platform.select({
  web: {
    backgroundColor: "rgba(243,244,244,0.72)",
    backdropFilter: "blur(20px) saturate(180%)",
    WebkitBackdropFilter: "blur(20px) saturate(180%)",
  } as unknown as ViewStyle,
  default: { backgroundColor: "rgba(243,244,244,0.96)" },
});

// iOS-style dynamic header: invisible at rest, fades in as the large title
// scrolls away. pointerEvents none so it never swallows touches.
export function GlassHeader({ title, scrollY }: { title: string; scrollY: Animated.Value }) {
  const insets = useSafeAreaInsets();
  const opacity = scrollY.interpolate({
    inputRange: [28, 64],
    outputRange: [0, 1],
    extrapolate: "clamp",
  });
  const translateY = scrollY.interpolate({
    inputRange: [28, 64],
    outputRange: [6, 0],
    extrapolate: "clamp",
  });

  return (
    <Animated.View
      pointerEvents="none"
      style={[
        styles.header,
        glassStyle,
        { paddingTop: insets.top, height: 44 + insets.top, opacity },
      ]}
    >
      <Animated.Text style={[styles.title, { transform: [{ translateY }] }]} numberOfLines={1}>
        {title}
      </Animated.Text>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  header: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    zIndex: 10,
    alignItems: "center",
    justifyContent: "center",
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "rgba(0,0,0,0.12)",
  },
  title: { fontSize: 16, fontFamily: fonts.sansBold, color: colors.inkPrimary, maxWidth: "70%" },
});
