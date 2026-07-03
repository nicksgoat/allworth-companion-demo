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
}: {
  title: string;
  scrollY?: Animated.Value;
  // Optional tap on the brand mark (chat uses it for thread history).
  onPressMark?: () => void;
  action?: { icon: keyof typeof Ionicons.glyphMap; onPress: () => void };
}) {
  const insets = useSafeAreaInsets();
  // Closed = just the status-bar glass strip; open = strip + title row. The
  // container's height animates between the two (clipping the row out), so
  // the title can never slide into the status bar.
  const clamp = scrollY ? Animated.diffClamp(scrollY, 0, APP_HEADER_HEIGHT) : null;
  const height = clamp
    ? clamp.interpolate({
        inputRange: [0, APP_HEADER_HEIGHT],
        outputRange: [insets.top + APP_HEADER_HEIGHT, insets.top],
      })
    : insets.top + APP_HEADER_HEIGHT;
  const rowOpacity = clamp
    ? clamp.interpolate({ inputRange: [0, APP_HEADER_HEIGHT], outputRange: [1, 0] })
    : 1;

  return (
    <Animated.View style={[styles.header, { height }]}>
      <GlassSurface
        style={[
          StyleSheet.absoluteFill as ViewStyle,
          styles.headerSurface,
          { paddingTop: insets.top },
        ]}
      >
        <Animated.View style={[styles.headerRow, { opacity: rowOpacity }]}>
          <Pressable
            onPress={onPressMark}
            disabled={!onPressMark}
            hitSlop={8}
            style={({ pressed }) => [
              styles.headerMark,
              pressed && onPressMark ? { opacity: 0.6 } : null,
            ]}
          >
            <AllworthMark size={18} color={colors.allworthNavy} />
          </Pressable>
          <Text style={styles.headerTitle} numberOfLines={1}>
            {title}
          </Text>
          {action ? (
            <Pressable
              onPress={action.onPress}
              hitSlop={8}
              style={({ pressed }) => [styles.headerBtn, pressed && { opacity: 0.6 }]}
            >
              <Ionicons name={action.icon} size={22} color={colors.inkPrimary} />
            </Pressable>
          ) : (
            <View style={styles.headerBtn} />
          )}
        </Animated.View>
      </GlassSurface>
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
