import React, { useRef } from "react";
import { Pressable } from "react-native";
import Svg, { Path } from "react-native-svg";
import { colors } from "../theme";
import { useApp } from "../state";
import { ACCENT_PATHS, LOGO_VIEWBOX, MARK_VIEWBOX, NAVY_PATHS } from "./logoPaths";

export function AllworthLogo({ width = 104, light }: { width?: number; light?: boolean }) {
  return (
    <Svg width={width} height={(width * 100) / 414} viewBox={LOGO_VIEWBOX}>
      {NAVY_PATHS.map((d, i) => (
        <Path key={`n${i}`} d={d} fill={light ? "#FFFFFF" : colors.allworthNavy} />
      ))}
      {ACCENT_PATHS.map((d, i) => (
        <Path key={`a${i}`} d={d} fill={light ? "#FFFFFF" : colors.allworthAccent} />
      ))}
    </Svg>
  );
}

export function AllworthMark({
  size = 28,
  color = colors.allworthAccent,
}: {
  size?: number;
  color?: string;
}) {
  return (
    <Svg width={size} height={size} viewBox={MARK_VIEWBOX}>
      {ACCENT_PATHS.map((d, i) => (
        <Path key={i} d={d} fill={color} />
      ))}
    </Svg>
  );
}

// The Allworth logo — triple-tap opens the hidden demo control sheet.
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
      <AllworthLogo light={light} />
    </Pressable>
  );
}
