import { Ionicons } from "@expo/vector-icons";
import { BlurView } from "expo-blur";
import React from "react";
import { Animated, Platform, Pressable, StyleSheet, Text, View, ViewStyle } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors, fonts, space } from "../theme";
import { AllworthMark } from "./Wordmark";

export const TAB_BAR_HEIGHT = 60;
export const APP_HEADER_HEIGHT = 48;

// Liquid-glass surface: react-native-web passes backdropFilter through to
// CSS; iOS gets a real BlurView via GlassSurface; Android falls back to a
// near-opaque wash.
export const glassStyle: ViewStyle = Platform.select({
  web: {
    backgroundColor: "rgba(243,244,244,0.72)",
    backdropFilter: "blur(20px) saturate(180%)",
    WebkitBackdropFilter: "blur(20px) saturate(180%)",
  } as unknown as ViewStyle,
  default: { backgroundColor: "rgba(243,244,244,0.96)" },
});

// The one translucent surface (DESIGN.md): real blur on iOS, CSS backdrop
// blur on web, opaque-ish wash on Android. Layout styles come from the
// caller; this only owns the material.
export function GlassSurface({
  style,
  children,
}: {
  style?: ViewStyle | (ViewStyle | undefined | false | null)[];
  children?: React.ReactNode;
}) {
  if (Platform.OS === "ios") {
    return (
      <BlurView
        intensity={42}
        tint="extraLight"
        style={[{ backgroundColor: "rgba(243,244,244,0.55)" }, style as ViewStyle]}
      >
        {children}
      </BlurView>
    );
  }
  return <View style={[glassStyle, style as ViewStyle]}>{children}</View>;
}

// The one global header (DESIGN.md): the chat pattern applied everywhere —
// brand mark chip + title on the left, one optional action on the right, on
// glass. Given a scrollY it animates closed (the title row slides away, the
// status-bar glass strip stays) as you scroll down and reopens the moment you
// scroll back up — Animated.diffClamp, so it tracks gesture direction, not
// absolute position.
export function AppHeader({
  title,
  scrollY,
  onPressMark,
  action,
  onHero,
  solid,
}: {
  title: string;
  scrollY?: Animated.Value;
  // Optional tap on the brand mark (chat uses it for thread history).
  onPressMark?: () => void;
  action?: { icon: keyof typeof Ionicons.glyphMap; onPress: () => void };
  // When the screen leads with a full-bleed navy hero (see NavyHeroBand): the
  // header floats transparent + white over the navy, then cross-fades to the
  // normal light glass header as the hero scrolls away.
  onHero?: boolean;
  // A solid navy header bar (white content) for surfaces without a hero band —
  // e.g. Chat, where a tall hero would eat the conversation. Same collapse
  // behavior as the default glass header.
  solid?: boolean;
}) {
  const insets = useSafeAreaInsets();

  // The mark chip + title + optional action, tinted for a given surface.
  const renderRow = (tint: {
    title: string;
    mark: string;
    markChip: string;
    action: string;
  }) => (
    <View style={styles.headerRow}>
      <Pressable
        onPress={onPressMark}
        disabled={!onPressMark}
        hitSlop={8}
        style={({ pressed }) => [
          styles.headerMark,
          { backgroundColor: tint.markChip },
          pressed && onPressMark ? { opacity: 0.6 } : null,
        ]}
      >
        <AllworthMark size={18} color={tint.mark} />
      </Pressable>
      <Text style={[styles.headerTitle, { color: tint.title }]} numberOfLines={1}>
        {title}
      </Text>
      {action ? (
        <Pressable
          onPress={action.onPress}
          hitSlop={8}
          style={({ pressed }) => [styles.headerBtn, pressed && { opacity: 0.6 }]}
        >
          <Ionicons name={action.icon} size={22} color={tint.action} />
        </Pressable>
      ) : (
        <View style={styles.headerBtn} />
      )}
    </View>
  );

  const DARK = { title: colors.inkPrimary, mark: colors.allworthNavy, markChip: "rgba(255,255,255,0.85)", action: colors.inkPrimary };
  const LIGHT = { title: "#FFFFFF", mark: "#FFFFFF", markChip: "rgba(255,255,255,0.16)", action: "#FFFFFF" };

  // Hero mode: fixed height; the glass background + dark content fade IN as the
  // navy hero scrolls away, while the white-on-navy content fades out. FADE is
  // roughly the hero's on-screen depth below the header.
  if (onHero) {
    const FADE = 130;
    const glass = scrollY
      ? scrollY.interpolate({ inputRange: [0, FADE], outputRange: [0, 1], extrapolate: "clamp" })
      : new Animated.Value(0);
    const overHero = scrollY
      ? scrollY.interpolate({ inputRange: [0, FADE], outputRange: [1, 0], extrapolate: "clamp" })
      : new Animated.Value(1);
    return (
      <View style={[styles.header, { height: insets.top + APP_HEADER_HEIGHT }]}>
        <Animated.View style={[StyleSheet.absoluteFill as ViewStyle, { opacity: glass }]}>
          <GlassSurface
            style={[
              StyleSheet.absoluteFill as ViewStyle,
              styles.headerSurface,
              { paddingTop: insets.top },
            ]}
          />
        </Animated.View>
        {/* Dark row over the glass (appears once scrolled). Interactive. */}
        <Animated.View style={[styles.headerLayer, { paddingTop: insets.top, opacity: glass }]}>
          {renderRow(DARK)}
        </Animated.View>
        {/* White row over the navy hero. Non-interactive: taps fall through to
            the dark row's Pressables underneath (same positions). */}
        <Animated.View
          pointerEvents="none"
          style={[styles.headerLayer, { paddingTop: insets.top, opacity: overHero }]}
        >
          {renderRow(LIGHT)}
        </Animated.View>
      </View>
    );
  }

  // Default: light glass header that collapses on scroll-down, reopens on
  // scroll-up (the title row clips out; the status-bar strip stays).
  // extrapolateLeft clamps out iOS rubber-band overscroll: without it, the
  // bounce settling back from negative to 0 reads as a scroll-down and closes
  // the header at the very top of the list.
  const clamp = scrollY
    ? Animated.diffClamp(
        scrollY.interpolate({
          inputRange: [0, 1],
          outputRange: [0, 1],
          extrapolateLeft: "clamp",
        }),
        0,
        APP_HEADER_HEIGHT,
      )
    : null;
  const height = clamp
    ? clamp.interpolate({
        inputRange: [0, APP_HEADER_HEIGHT],
        outputRange: [insets.top + APP_HEADER_HEIGHT, insets.top],
      })
    : insets.top + APP_HEADER_HEIGHT;
  const rowOpacity = clamp
    ? clamp.interpolate({ inputRange: [0, APP_HEADER_HEIGHT], outputRange: [1, 0] })
    : 1;

  const surfaceStyle = [
    StyleSheet.absoluteFill as ViewStyle,
    styles.headerSurface,
    { paddingTop: insets.top },
  ];
  const row = (
    <Animated.View style={{ opacity: rowOpacity }}>{renderRow(solid ? LIGHT : DARK)}</Animated.View>
  );

  return (
    <Animated.View style={[styles.header, { height }]}>
      {solid ? (
        <View style={[surfaceStyle, styles.solidSurface]}>{row}</View>
      ) : (
        <GlassSurface style={surfaceStyle}>{row}</GlassSurface>
      )}
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
  },
  headerSurface: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "rgba(0,0,0,0.12)",
    overflow: "hidden",
  },
  solidSurface: {
    backgroundColor: colors.chartNightBlue,
    borderBottomColor: "rgba(255,255,255,0.10)",
  },
  headerLayer: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
  },
  headerRow: {
    height: APP_HEADER_HEIGHT,
    flexDirection: "row",
    alignItems: "center",
    gap: space[2],
    paddingHorizontal: space[4],
  },
  headerMark: {
    width: 32,
    height: 32,
    borderRadius: 10,
    backgroundColor: "rgba(255,255,255,0.85)",
    alignItems: "center",
    justifyContent: "center",
  },
  headerTitle: {
    flex: 1,
    fontSize: 17,
    fontFamily: fonts.sansBold,
    color: colors.inkPrimary,
  },
  headerBtn: {
    width: 36,
    height: 36,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
  },
});
