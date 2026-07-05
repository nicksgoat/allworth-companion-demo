import { Ionicons } from "@expo/vector-icons";
import React, { useState } from "react";
import { LayoutChangeEvent, Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Svg, { Defs, LinearGradient, RadialGradient, Rect, Stop } from "react-native-svg";
import { colors, fonts, space } from "../theme";
import { APP_HEADER_HEIGHT } from "./Glass";

// The scroll-container gutter both tab screens use (contentContainer padding).
// The band cancels it with negative margins to bleed to the screen edges.
const GUTTER = space[5]; // 20

// The brand's premium hero fill — Night Blue → Indigo gradient with a soft
// cerulean glow, the surface treatment the design deck reserves for hero/premium
// backgrounds. Rendered as an absolute-fill layer that measures its own parent,
// so any navy band can drop it in behind content (parent needs `overflow:
// hidden` for rounded corners). `id` must be unique per mounted instance —
// react-native-web emits real DOM SVG, so two instances sharing a fragment id
// would collide; the tab screens are mounted simultaneously.
export function NavyGradient({ id }: { id: string }) {
  const [size, setSize] = useState({ w: 0, h: 0 });
  return (
    <View
      pointerEvents="none"
      style={StyleSheet.absoluteFill}
      onLayout={(e: LayoutChangeEvent) =>
        setSize({ w: e.nativeEvent.layout.width, h: e.nativeEvent.layout.height })
      }
    >
      {size.w > 0 ? (
        <Svg width={size.w} height={size.h}>
          <Defs>
            <LinearGradient id={`${id}Bg`} x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor={colors.chartNightBlue} />
              <Stop offset="1" stopColor={colors.allworthNavy} />
            </LinearGradient>
            <RadialGradient id={`${id}Glow`} cx="82%" cy="12%" r="70%">
              <Stop offset="0" stopColor={colors.allworthAccent} stopOpacity={0.36} />
              <Stop offset="1" stopColor={colors.allworthAccent} stopOpacity={0} />
            </RadialGradient>
          </Defs>
          <Rect x={0} y={0} width={size.w} height={size.h} fill={`url(#${id}Bg)`} />
          <Rect x={0} y={0} width={size.w} height={size.h} fill={`url(#${id}Glow)`} />
        </Svg>
      ) : null}
    </View>
  );
}

// Full-bleed navy hero band: the premium navy surface reaching the top and side
// screen edges (not an inset card), with a rounded bottom lip. Used as the first
// module on a tab screen. It cancels the scroll container's top + horizontal
// padding to bleed to the edges, then re-adds inner padding so its content clears
// the (transparent-over-hero) AppHeader. Pair with `<AppHeader onHero />` so the
// header floats white over the navy and fades to glass on scroll.
export function NavyHeroBand({ id, children }: { id: string; children: React.ReactNode }) {
  const insets = useSafeAreaInsets();
  return (
    <View
      style={[
        styles.band,
        {
          // Cancel the scroll container's paddingTop (insets.top + header + 8)
          // so the navy reaches the very top edge, behind the status bar.
          marginTop: -(insets.top + APP_HEADER_HEIGHT + space[2]),
          // Re-add that space inside so content sits below the header zone.
          paddingTop: insets.top + APP_HEADER_HEIGHT + space[4],
        },
      ]}
    >
      <NavyGradient id={id} />
      {children}
    </View>
  );
}

// The Home greeting hero — the brand's premium Night Blue → Indigo surface
// carrying only the greeting, advisor presence, and a way into Wealth. No
// net-worth figure or trajectory chart lives here: both are barred at screen
// level (DESIGN.md). The combined number + chart live in the tapped-in
// NetWorthDetail off Wealth.
export function GreetingHero({
  greeting,
  name,
  advisorLine,
  onOpenWealth,
}: {
  greeting: string;
  name: string;
  advisorLine: string;
  onOpenWealth: () => void;
}) {
  return (
    <NavyHeroBand id="homeHero">
      <View style={styles.greetingBlock}>
        <Text style={styles.salutation}>{greeting},</Text>
        <Text style={styles.name} numberOfLines={1} adjustsFontSizeToFit>
          {name}
        </Text>
      </View>

      <View style={styles.advisorRow}>
        <Ionicons name="person-circle-outline" size={16} color="rgba(255,255,255,0.72)" />
        <Text style={styles.advisorText} numberOfLines={1}>
          {advisorLine}
        </Text>
      </View>

      <Pressable
        onPress={onOpenWealth}
        hitSlop={8}
        style={({ pressed }) => [styles.link, pressed && { opacity: 0.7 }]}
      >
        <Text style={styles.linkText}>View your wealth</Text>
        <Ionicons name="chevron-forward" size={14} color="rgba(255,255,255,0.92)" />
      </Pressable>
    </NavyHeroBand>
  );
}

const styles = StyleSheet.create({
  band: {
    backgroundColor: colors.chartNightBlue,
    marginHorizontal: -GUTTER, // bleed to both side edges
    paddingHorizontal: GUTTER, // keep content aligned with the rest of the screen
    paddingBottom: space[5],
    borderBottomLeftRadius: 28,
    borderBottomRightRadius: 28,
    overflow: "hidden",
    gap: space[3],
  },
  greetingBlock: { gap: 2 },
  salutation: {
    fontSize: 14,
    fontFamily: fonts.sans,
    color: "rgba(255,255,255,0.72)",
    letterSpacing: 0.2,
  },
  name: { fontSize: 30, fontFamily: fonts.displayMedium, color: "#FFFFFF" },
  advisorRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  advisorText: { fontSize: 13, fontFamily: fonts.sans, color: "rgba(255,255,255,0.82)" },
  link: { flexDirection: "row", alignItems: "center", gap: 3, marginTop: space[1] },
  linkText: { fontSize: 14, fontFamily: fonts.sansBold, color: "rgba(255,255,255,0.92)" },
});
