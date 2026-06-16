import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import React, { useMemo, useState } from "react";
import { LayoutChangeEvent, Modal, Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Svg, { Circle, Defs, LinearGradient, Line, Path, Stop } from "react-native-svg";
import { densify } from "../chartData";
import { colors, fonts, monthLabel, usd } from "../theme";
import type { Dashboard, MonthValue } from "../types";
import { AllworthMark } from "./Wordmark";

const RANGES = [
  { label: "3M", points: 3, suffix: "past 3 months" },
  { label: "6M", points: 6, suffix: "past 6 months" },
  { label: "1Y", points: 12, suffix: "past year" },
];

// Full-bleed account-value chart — a bold white line over a navy field, with a
// dotted baseline at the start-of-range value and drag-to-scrub. (Acorns-style.)
function BigChart({ points }: { points: MonthValue[] }) {
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [sel, setSel] = useState<number | null>(null);

  // Resample the coarse monthly anchors into a dense, smooth, organic series.
  const dense = useMemo(() => densify(points, 18), [points]);

  const geom = useMemo(() => {
    if (!size.w || !size.h || dense.length < 2) return null;
    const values = dense.map((p) => p.value);
    const lo = Math.min(...values);
    const hi = Math.max(...values);
    const pad = (hi - lo) / 6 || 1;
    const yMin = lo - pad;
    const yMax = hi + pad;
    const x = (i: number) => (i / (dense.length - 1)) * size.w;
    const y = (v: number) => size.h - ((v - yMin) / (yMax - yMin)) * size.h;
    const coords = dense.map((p, i) => ({ x: x(i), y: y(p.value) }));
    let line = `M ${coords[0].x.toFixed(2)} ${coords[0].y.toFixed(2)}`;
    for (let i = 1; i < coords.length; i++) {
      line += ` L ${coords[i].x.toFixed(2)} ${coords[i].y.toFixed(2)}`;
    }
    return {
      coords,
      line,
      area: `${line} L ${size.w} ${size.h} L 0 ${size.h} Z`,
      baselineY: coords[0].y,
      last: coords[coords.length - 1],
    };
  }, [size, dense]);

  const select = (locationX: number) => {
    if (!size.w || dense.length < 2) return;
    const i = Math.max(0, Math.min(dense.length - 1, Math.round((locationX / size.w) * (dense.length - 1))));
    setSel((prev) => {
      if (prev !== i) Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
      return i;
    });
  };

  return (
    <View
      style={{ flex: 1 }}
      onLayout={(e: LayoutChangeEvent) =>
        setSize({ w: e.nativeEvent.layout.width, h: e.nativeEvent.layout.height })
      }
      onStartShouldSetResponder={() => true}
      onMoveShouldSetResponder={() => true}
      onResponderGrant={(e) => select(e.nativeEvent.locationX)}
      onResponderMove={(e) => select(e.nativeEvent.locationX)}
      onResponderRelease={() => setSel(null)}
    >
      {sel != null ? (
        <Text style={styles.scrub}>
          {usd(dense[sel].value)} · {monthLabel(dense[sel].month)}
        </Text>
      ) : null}
      {geom ? (
        <Svg width={size.w} height={size.h}>
          <Defs>
            <LinearGradient id="nwfill" x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor="#FFFFFF" stopOpacity={0.18} />
              <Stop offset="1" stopColor="#FFFFFF" stopOpacity={0} />
            </LinearGradient>
          </Defs>
          <Path d={geom.area} fill="url(#nwfill)" />
          <Line
            x1={0}
            y1={geom.baselineY}
            x2={size.w}
            y2={geom.baselineY}
            stroke="#FFFFFF"
            strokeWidth={1}
            strokeDasharray="2 6"
            strokeOpacity={0.4}
          />
          {/* Soft halo + crisp line */}
          <Path
            d={geom.line}
            stroke="#FFFFFF"
            strokeWidth={8}
            strokeOpacity={0.12}
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <Path
            d={geom.line}
            stroke="#FFFFFF"
            strokeWidth={3}
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          {sel == null ? (
            <>
              <Circle cx={geom.last.x} cy={geom.last.y} r={8} fill="#FFFFFF" fillOpacity={0.2} />
              <Circle cx={geom.last.x} cy={geom.last.y} r={4} fill="#FFFFFF" />
            </>
          ) : (
            <>
              <Line x1={geom.coords[sel].x} y1={0} x2={geom.coords[sel].x} y2={size.h} stroke="#FFFFFF" strokeOpacity={0.3} strokeWidth={1} />
              <Circle cx={geom.coords[sel].x} cy={geom.coords[sel].y} r={6} fill="#FFFFFF" />
            </>
          )}
        </Svg>
      ) : null}
    </View>
  );
}

export function NetWorthDetail({
  visible,
  onClose,
  d,
}: {
  visible: boolean;
  onClose: () => void;
  d: Dashboard;
}) {
  const insets = useSafeAreaInsets();
  const [range, setRange] = useState("1Y");

  const { slice, delta } = useMemo(() => {
    const history = d.netWorthHistory;
    const spec = RANGES.find((r) => r.label === range) ?? RANGES[RANGES.length - 1];
    const sliced = history.length >= spec.points ? history.slice(-spec.points) : history;
    if (sliced.length < 2) return { slice: sliced, delta: undefined };
    const diff = sliced[sliced.length - 1].value - sliced[0].value;
    const pct = sliced[0].value ? (diff / sliced[0].value) * 100 : 0;
    return {
      slice: sliced,
      delta: {
        text: `${diff >= 0 ? "+" : "−"}${usd(Math.abs(diff))} (${diff >= 0 ? "+" : "−"}${Math.abs(pct).toFixed(1)}%) ${spec.suffix}`,
        positive: diff >= 0,
      },
    };
  }, [d.netWorthHistory, range]);

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose} presentationStyle="fullScreen">
      <View style={[styles.container, { paddingTop: insets.top + 6, paddingBottom: insets.bottom + 16 }]}>
        <View style={styles.topBar}>
          <Pressable onPress={onClose} hitSlop={12}>
            <Ionicons name="close" size={26} color="#FFFFFF" />
          </Pressable>
          <View style={{ alignItems: "center" }}>
            <Text style={styles.topTitle}>Net worth</Text>
            <Text style={styles.topSub}>as of today</Text>
          </View>
          <AllworthMark size={22} color="#FFFFFF" />
        </View>

        <View style={styles.valueBlock}>
          <Text style={styles.bigValue}>{usd(d.netWorth)}</Text>
          {delta ? (
            <Text
              style={[styles.delta, { color: delta.positive ? colors.gainOnDark : colors.lossOnDark }]}
            >
              {delta.positive ? "↑" : "↓"} {delta.text}
            </Text>
          ) : null}
        </View>

        <BigChart points={slice} />

        <View style={styles.ranges}>
          {RANGES.map((r) => {
            const on = r.label === range;
            return (
              <Pressable key={r.label} onPress={() => setRange(r.label)} hitSlop={8} style={[styles.rangeChip, on && styles.rangeChipOn]}>
                <Text style={[styles.rangeText, on && styles.rangeTextOn]}>{r.label}</Text>
              </Pressable>
            );
          })}
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.chartNightBlue, paddingHorizontal: 20, gap: 18 },
  topBar: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  topTitle: { fontSize: 16, fontFamily: fonts.sansBold, color: "#FFFFFF" },
  topSub: { fontSize: 12, fontFamily: fonts.sans, color: "rgba(255,255,255,0.6)", marginTop: 1 },
  valueBlock: { gap: 6 },
  bigValue: {
    fontSize: 44,
    fontFamily: fonts.display,
    color: "#FFFFFF",
    fontVariant: ["tabular-nums"],
  },
  delta: { fontSize: 17, fontFamily: fonts.sansBold, fontVariant: ["tabular-nums"] },
  scrub: {
    position: "absolute",
    top: -2,
    left: 0,
    zIndex: 1,
    fontSize: 14,
    fontFamily: fonts.sansBold,
    color: "#FFFFFF",
    fontVariant: ["tabular-nums"],
  },
  ranges: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  rangeChip: { flex: 1, alignItems: "center", paddingVertical: 8, borderRadius: 8 },
  rangeChipOn: { backgroundColor: "rgba(255,255,255,0.15)" },
  rangeText: { fontSize: 15, fontFamily: fonts.sansBold, color: "rgba(255,255,255,0.55)" },
  rangeTextOn: { color: "#FFFFFF" },
});
