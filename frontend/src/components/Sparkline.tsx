import * as Haptics from "expo-haptics";
import React, { useEffect, useId, useMemo, useRef, useState } from "react";
import { LayoutChangeEvent, StyleSheet, Text, View } from "react-native";
import Svg, { Circle, ClipPath, Defs, LinearGradient, Line, Path, Rect, Stop } from "react-native-svg";
import { densify } from "../chartData";
import { colors, fonts, monthLabel, usd } from "../theme";
import type { MonthValue } from "../types";

const HEIGHT = 92;

export function Sparkline({
  points,
  lineColor = colors.allworthNavy,
}: {
  points: MonthValue[];
  lineColor?: string;
}) {
  const [width, setWidth] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const [reveal, setReveal] = useState(0);

  // Unique per instance — sheets and screens can each mount a sparkline,
  // and duplicate SVG ids resolve to the first match in the document on web.
  const uid = useId().replace(/:/g, "");
  const fillId = `sparkfill-${uid}`;
  const clipId = `sparkclip-${uid}`;

  // Resample the coarse monthly anchors into a dense, smooth, organic series.
  const dense = useMemo(() => densify(points), [points]);

  // Left-to-right draw-in, re-triggered when the range changes.
  useEffect(() => {
    const start = Date.now();
    const duration = 720;
    let raf = 0;
    const tick = () => {
      const t = Math.min(1, (Date.now() - start) / duration);
      setReveal(1 - Math.pow(1 - t, 3));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [dense]);

  const geom = useMemo(() => {
    if (!width || dense.length < 2) return null;
    const values = dense.map((p) => p.value);
    const lo = Math.min(...values);
    const hi = Math.max(...values);
    const pad = (hi - lo) / 4 || 1;
    const yMin = lo - pad;
    const yMax = hi + pad;
    const x = (i: number) => (i / (dense.length - 1)) * width;
    const y = (v: number) => HEIGHT - ((v - yMin) / (yMax - yMin)) * HEIGHT;
    const coords = dense.map((p, i) => ({ x: x(i), y: y(p.value) }));
    // Dense enough (~150 pts) that straight segments read as a glass-smooth line,
    // while inheriting the no-overshoot shape from the monotone resampling.
    let line = `M ${coords[0].x.toFixed(2)} ${coords[0].y.toFixed(2)}`;
    for (let i = 1; i < coords.length; i++) {
      line += ` L ${coords[i].x.toFixed(2)} ${coords[i].y.toFixed(2)}`;
    }
    const area = `${line} L ${width} ${HEIGHT} L 0 ${HEIGHT} Z`;
    return { coords, line, area, last: coords[coords.length - 1] };
  }, [width, dense]);

  const onLayout = (e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width);

  const select = (locationX: number) => {
    if (!width || dense.length < 2) return;
    const i = Math.round((locationX / width) * (dense.length - 1));
    const clamped = Math.max(0, Math.min(dense.length - 1, i));
    setSelected((prev) => {
      if (prev !== clamped) Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
      return clamped;
    });
  };

  const sel = selected != null && geom ? geom.coords[selected] : null;

  // Only capture the gesture once it's clearly a horizontal scrub — otherwise a
  // vertical drag stays with the page's ScrollView. Without this the chart eats
  // every touch that starts on it and the page won't scroll.
  const start = useRef({ x: 0, y: 0 });
  const claimHorizontal = (e: any) => {
    const dx = Math.abs(e.nativeEvent.pageX - start.current.x);
    const dy = Math.abs(e.nativeEvent.pageY - start.current.y);
    return dx > 8 && dx > dy;
  };

  return (
    <View
      style={styles.container}
      onLayout={onLayout}
      onStartShouldSetResponder={(e) => {
        start.current = { x: e.nativeEvent.pageX, y: e.nativeEvent.pageY };
        return false; // don't grab on touch-down — let the page scroll
      }}
      onMoveShouldSetResponder={claimHorizontal}
      onResponderGrant={(e) => select(e.nativeEvent.locationX)}
      onResponderMove={(e) => select(e.nativeEvent.locationX)}
      onResponderRelease={() => setSelected(null)}
      onResponderTerminate={() => setSelected(null)}
    >
      {geom ? (
        <Svg width={width} height={HEIGHT}>
          <Defs>
            <LinearGradient id={fillId} x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor={lineColor} stopOpacity={0.18} />
              <Stop offset="1" stopColor={lineColor} stopOpacity={0} />
            </LinearGradient>
            <ClipPath id={clipId}>
              <Rect x={0} y={0} width={width * reveal} height={HEIGHT} />
            </ClipPath>
          </Defs>
          <Path d={geom.area} fill={`url(#${fillId})`} clipPath={`url(#${clipId})`} />
          {/* Soft halo under the line for a premium, lifted feel */}
          <Path
            d={geom.line}
            stroke={lineColor}
            strokeWidth={6}
            strokeOpacity={0.1}
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
            clipPath={`url(#${clipId})`}
          />
          <Path
            d={geom.line}
            stroke={lineColor}
            strokeWidth={2.5}
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
            clipPath={`url(#${clipId})`}
          />
          {/* Live dot at the latest value when idle */}
          {!sel && reveal >= 1 ? (
            <>
              <Circle cx={geom.last.x} cy={geom.last.y} r={6} fill={lineColor} fillOpacity={0.16} />
              <Circle cx={geom.last.x} cy={geom.last.y} r={3.5} fill={lineColor} />
            </>
          ) : null}
          {/* Scrub guide */}
          {sel ? (
            <>
              <Line x1={sel.x} y1={0} x2={sel.x} y2={HEIGHT} stroke={lineColor} strokeOpacity={0.22} strokeWidth={1} />
              <Circle cx={sel.x} cy={sel.y} r={5} fill={lineColor} stroke="#FFFFFF" strokeWidth={2} />
            </>
          ) : null}
        </Svg>
      ) : null}
      {selected != null ? (
        <Text style={[styles.scrubLabel, { color: lineColor }]}>
          {usd(dense[selected].value)} · {monthLabel(dense[selected].month)}
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
