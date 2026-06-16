import { Ionicons } from "@expo/vector-icons";
import React, { useState } from "react";
import { LayoutChangeEvent, Pressable, StyleSheet, Text, View } from "react-native";
import Svg, { Defs, LinearGradient, RadialGradient, Rect, Stop } from "react-native-svg";
import { useCountUp } from "../anim";
import { colors, fonts, usd } from "../theme";
import type { MonthValue } from "../types";
import { Sparkline } from "./Sparkline";

const POS = "#86C98A"; // light evergreen — readable on the navy field
const NEG = "#E89B73"; // light pumpkin

// The net-worth hero — a full-bleed Night Blue → Indigo gradient header (the
// brand's premium surface) carrying the greeting, net worth, and chart, instead
// of a light card. Bleeds past the scroll padding to the screen edges.
export function NetWorthHero({
  greeting,
  name,
  initials,
  netWorth,
  delta,
  history,
  insetsTop,
  scrollPadding = 20,
  onOpenWealth,
  onAvatarPress,
}: {
  greeting: string;
  name: string;
  initials: string;
  netWorth: number;
  delta?: { text: string; positive: boolean };
  history: MonthValue[];
  insetsTop: number;
  scrollPadding?: number;
  onOpenWealth: () => void;
  onAvatarPress: () => void;
}) {
  const displayed = useCountUp(netWorth);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const onLayout = (e: LayoutChangeEvent) =>
    setSize({ w: e.nativeEvent.layout.width, h: e.nativeEvent.layout.height });

  return (
    <View
      onLayout={onLayout}
      style={[
        styles.band,
        {
          marginTop: -(insetsTop + 8), // cancel the scroll container's top padding → reach the top edge
          marginHorizontal: -scrollPadding, // bleed to the screen edges
          paddingTop: insetsTop + 18,
          paddingHorizontal: scrollPadding,
        },
      ]}
    >
      {size.w > 0 ? (
        <Svg style={StyleSheet.absoluteFill} width={size.w} height={size.h}>
          <Defs>
            <LinearGradient id="nwHeroBg" x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor={colors.chartNightBlue} />
              <Stop offset="1" stopColor={colors.allworthNavy} />
            </LinearGradient>
            <RadialGradient id="nwHeroGlow" cx="78%" cy="14%" r="65%">
              <Stop offset="0" stopColor={colors.allworthAccent} stopOpacity={0.34} />
              <Stop offset="1" stopColor={colors.allworthAccent} stopOpacity={0} />
            </RadialGradient>
          </Defs>
          <Rect x={0} y={0} width={size.w} height={size.h} fill="url(#nwHeroBg)" />
          <Rect x={0} y={0} width={size.w} height={size.h} fill="url(#nwHeroGlow)" />
        </Svg>
      ) : null}

      <View style={styles.topRow}>
        <View style={styles.greetingBlock}>
          <Text style={styles.salutation}>{greeting}</Text>
          <Text style={styles.name} numberOfLines={1} adjustsFontSizeToFit>
            {name}
          </Text>
        </View>
        <Pressable
          onPress={onAvatarPress}
          hitSlop={8}
          style={({ pressed }) => [styles.avatar, pressed && { opacity: 0.85 }]}
        >
          <Text style={styles.avatarInitials}>{initials}</Text>
        </Pressable>
      </View>

      <Pressable
        onPress={onOpenWealth}
        style={({ pressed }) => [styles.nwBlock, pressed && { opacity: 0.85 }]}
      >
        <Text style={styles.nwLabel}>Net worth</Text>
        <Text style={styles.nwValue}>{usd(displayed)}</Text>
        {delta ? (
          <Text style={[styles.nwDelta, { color: delta.positive ? POS : NEG }]}>
            {delta.positive ? "↑" : "↓"} {delta.text}
          </Text>
        ) : null}
      </Pressable>

      <View style={styles.chart}>
        <Sparkline points={history} lineColor="#FFFFFF" />
      </View>

      <Pressable
        onPress={onOpenWealth}
        hitSlop={8}
        style={({ pressed }) => [styles.link, pressed && { opacity: 0.7 }]}
      >
        <Text style={styles.linkText}>View your wealth</Text>
        <Ionicons name="chevron-forward" size={14} color="rgba(255,255,255,0.9)" />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  band: {
    backgroundColor: colors.chartNightBlue,
    paddingBottom: 20,
    borderBottomLeftRadius: 28,
    borderBottomRightRadius: 28,
    overflow: "hidden",
    gap: 14,
  },
  topRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12 },
  greetingBlock: { flexShrink: 1, gap: 2 },
  salutation: {
    fontSize: 14,
    fontFamily: fonts.sans,
    color: "rgba(255,255,255,0.72)",
    letterSpacing: 0.2,
  },
  name: { fontSize: 25, fontFamily: fonts.displayMedium, color: "#FFFFFF" },
  avatar: {
    width: 46,
    height: 46,
    borderRadius: 23,
    backgroundColor: "rgba(255,255,255,0.16)",
    alignItems: "center",
    justifyContent: "center",
  },
  avatarInitials: { fontSize: 16, fontFamily: fonts.sansBold, color: "#FFFFFF", letterSpacing: 0.5 },

  nwBlock: { gap: 4, paddingTop: 4 },
  nwLabel: {
    fontSize: 12.5,
    fontFamily: fonts.sansBold,
    color: "rgba(255,255,255,0.6)",
    letterSpacing: 1,
    textTransform: "uppercase",
  },
  nwValue: {
    fontSize: 40,
    fontFamily: fonts.displayMedium,
    color: "#FFFFFF",
    fontVariant: ["tabular-nums"],
  },
  nwDelta: { fontSize: 15, fontFamily: fonts.sansBold, fontVariant: ["tabular-nums"] },

  chart: { marginTop: 2 },
  link: { flexDirection: "row", alignItems: "center", gap: 2 },
  linkText: { fontSize: 14, fontFamily: fonts.sansBold, color: "rgba(255,255,255,0.92)" },
});
