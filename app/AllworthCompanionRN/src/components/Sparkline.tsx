import * as Haptics from "expo-haptics";
import React, { useMemo, useState } from "react";
import { LayoutChangeEvent, StyleSheet, Text, View } from "react-native";
import Svg, { Circle, Defs, LinearGradient, Path, Stop } from "react-native-svg";
import { colors, fonts, monthLabel, usd } from "../theme";
import type { MonthValue } from "../types";

const HEIGHT = 88;

export function Sparkline({
  points,
  lineColor = colors.allworthNavy,
}: {
  points: MonthValue[];
  lineColor?: string;
}) {
  const [width, setWidth] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);

  const geom = useMemo(() => {
    if (!width || points.length < 2) return null;
    const values = points.map((p) => p.value);
    const lo = Math.min(...values);
    const hi = Math.max(...values);
    const pad = (hi - lo) / 4 || 1;
    const yMin = lo - pad;
    const yMax = hi + pad;
    const x = (i: number) => (i / (points.length - 1)) * width;
    const y = (v: number) => HEIGHT - ((v - yMin) / (yMax - yMin)) * HEIGHT;
    const coords = points.map((p, i) => ({ x: x(i), y: y(p.value) }));

    // Catmull-Rom → cubic bezier, matching the Swift chart's smoothing
    let line = `M ${coords[0].x} ${coords[0].y}`;
    for (let i = 0; i < coords.length - 1; i++) {
      const p0 = coords[Math.max(0, i - 1)];
      const p1 = coords[i];
      const p2 = coords[i + 1];
      const p3 = coords[Math.min(coords.length - 1, i + 2)];
      const c1x = p1.x + (p2.x - p0.x) / 6;
      const c1y = p1.y + (p2.y - p0.y) / 6;
      const c2x = p2.x - (p3.x - p1.x) / 6;
      const c2y = p2.y - (p3.y - p1.y) / 6;
      line += ` C ${c1x} ${c1y}, ${c2x} ${c2y}, ${p2.x} ${p2.y}`;
    }
    const area = `${line} L ${width} ${HEIGHT} L 0 ${HEIGHT} Z`;
    return { coords, line, area };
  }, [width, points]);

  const onLayout = (e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width);

  const select = (locationX: number) => {
    if (!width || points.length < 2) return;
    const i = Math.round((locationX / width) * (points.length - 1));
    const clamped = Math.max(0, Math.min(points.length - 1, i));
    setSelected((prev) => {
      if (prev !== clamped) Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
      return clamped;
    });
  };

  return (
    <View
      style={styles.container}
      onLayout={onLayout}
      onStartShouldSetResponder={() => true}
      onMoveShouldSetResponder={() => true}
      onResponderGrant={(e) => select(e.nativeEvent.locationX)}
      onResponderMove={(e) => select(e.nativeEvent.locationX)}
      onResponderRelease={() => setSelected(null)}
    >
      {geom ? (
        <Svg width={width} height={HEIGHT}>
          <Defs>
            <LinearGradient id="sparkfill" x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor={lineColor} stopOpacity={0.14} />
              <Stop offset="1" stopColor={lineColor} stopOpacity={0} />
            </LinearGradient>
          </Defs>
          <Path d={geom.area} fill="url(#sparkfill)" />
          <Path d={geom.line} stroke={lineColor} strokeWidth={2} fill="none" />
          {selected != null ? (
            <Circle
              cx={geom.coords[selected].x}
              cy={geom.coords[selected].y}
              r={4}
              fill={lineColor}
            />
          ) : null}
        </Svg>
      ) : null}
      {selected != null ? (
        <Text style={styles.scrubLabel}>
          {usd(points[selected].value)} · {monthLabel(points[selected].month)}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { height: HEIGHT, overflow: "hidden" },
  scrubLabel: {
    position: "absolute",
    top: 0,
    left: 0,
    fontSize: 13,
    fontFamily: fonts.sansBold,
    color: colors.inkSecondary,
    fontVariant: ["tabular-nums"],
  },
});
