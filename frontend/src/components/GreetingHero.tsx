import { Ionicons } from "@expo/vector-icons";
import React, { useEffect, useState } from "react";
import { Animated, Easing, LayoutChangeEvent, Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Svg, { Defs, LinearGradient, RadialGradient, Rect, Stop } from "react-native-svg";
import { useAnimatedValue } from "../anim";
import { colors, fonts, space } from "../theme";
import { APP_HEADER_HEIGHT } from "./Glass";
import { AllworthLogo } from "./Wordmark";

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
  scrollY,
}: {
  greeting: string;
  name: string;
  advisorLine: string;
  onOpenWealth: () => void;
  // Home's scroll position — drives the logo "handoff" into the header mark.
  scrollY?: Animated.Value;
}) {
  // "A real hello": on mount the hero fades up — the logo first, the words a
  // beat later — so landing on Home feels like a greeting, not a paint.
  const enterLogo = useAnimatedValue(0);
  const enterText = useAnimatedValue(0);
  useEffect(() => {
    Animated.timing(enterLogo, {
      toValue: 1,
      duration: 560,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: false,
    }).start();
    Animated.timing(enterText, {
      toValue: 1,
      duration: 560,
      delay: 150,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: false,
    }).start();
  }, [enterLogo, enterText]);

  // The main logo hands off to the small header mark: as the hero scrolls away
  // it shrinks up and fades over the first ~90px, right as `<AppHeader onHero
  // heroReveal>` resolves its compact mark in. One logo becoming the other.
  const sy = scrollY ?? new Animated.Value(0);
  const logoScroll = sy.interpolate({ inputRange: [0, 90], outputRange: [1, 0], extrapolate: "clamp" });
  const logoScale = sy.interpolate({ inputRange: [0, 90], outputRange: [1, 0.82], extrapolate: "clamp" });
  const logoLift = sy.interpolate({ inputRange: [0, 90], outputRange: [0, -10], extrapolate: "clamp" });
  const rise = (v: Animated.Value, from: number) =>
    v.interpolate({ inputRange: [0, 1], outputRange: [from, 0] });

  const advisorFirst = advisorLine.split(/[\s·]+/)[0] || advisorLine;

  return (
    <NavyHeroBand id="homeHero">
      {/* The main brand logo — the hello, which recedes into the header mark. */}
      <Animated.View
        style={{
          alignSelf: "flex-start",
          opacity: Animated.multiply(enterLogo, logoScroll),
          transform: [{ scale: logoScale }, { translateY: Animated.add(rise(enterLogo, 8), logoLift) }],
        }}
      >
        <AllworthLogo light width={150} />
      </Animated.View>

      <Animated.View
        style={{ gap: space[3], opacity: enterText, transform: [{ translateY: rise(enterText, 14) }] }}
      >
        <View style={styles.greetingBlock}>
          <Text style={styles.salutation}>{greeting},</Text>
          <Text style={styles.name} numberOfLines={1} adjustsFontSizeToFit>
            {name}
          </Text>
        </View>

        {/* Reassurance is carried by the warm surface + the human attestation,
            not a literal "you're safe" line. */}
        <View style={styles.chip}>
          <Ionicons name="shield-checkmark" size={13} color={colors.allworthAccent} />
          <Text style={styles.chipText}>Reviewed by {advisorFirst} this week</Text>
        </View>

        <Pressable
          onPress={onOpenWealth}
          hitSlop={8}
          style={({ pressed }) => [styles.link, pressed && { opacity: 0.7 }]}
        >
          <Text style={styles.linkText}>View your wealth</Text>
          <Ionicons name="chevron-forward" size={14} color="rgba(255,255,255,0.92)" />
        </Pressable>
      </Animated.View>
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
  chip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    alignSelf: "flex-start",
    paddingHorizontal: 11,
    paddingVertical: 6,
    borderRadius: 999,
    backgroundColor: "rgba(255,255,255,0.10)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.16)",
  },
  chipText: { fontSize: 12.5, fontFamily: fonts.sansBold, color: "rgba(255,255,255,0.9)" },
  link: { flexDirection: "row", alignItems: "center", gap: 3, marginTop: space[1] },
  linkText: { fontSize: 14, fontFamily: fonts.sansBold, color: "rgba(255,255,255,0.92)" },
});
