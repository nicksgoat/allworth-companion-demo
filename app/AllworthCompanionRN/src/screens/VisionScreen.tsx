import { Ionicons } from "@expo/vector-icons";
import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Svg, { Defs, LinearGradient, Rect, Stop } from "react-native-svg";
import { AllworthWordmark } from "../components/Wordmark";
import { colors, fonts } from "../theme";

// Premium dark surfaces use the Night Blue → Indigo gradient (brand deck p.7)
function BrandGradient() {
  return (
    <Svg style={StyleSheet.absoluteFill}>
      <Defs>
        <LinearGradient id="visionbg" x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor={colors.chartNightBlue} />
          <Stop offset="1" stopColor={colors.allworthNavy} />
        </LinearGradient>
      </Defs>
      <Rect x="0" y="0" width="100%" height="100%" fill="url(#visionbg)" />
    </Svg>
  );
}

// Beat 6 — static vision screen: "What the funded platform becomes."
export function VisionScreen() {
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.root, { paddingTop: insets.top + 24, paddingBottom: insets.bottom + 36 }]}>
      <BrandGradient />
      <View style={{ alignItems: "center" }}>
        <AllworthWordmark light />
        <Text style={styles.subtitle}>What the funded platform becomes</Text>
      </View>

      <View style={styles.diagram}>
        <View style={styles.dashedCircle} />
        <View style={styles.core}>
          <Ionicons name="bulb-outline" size={30} color="#fff" />
          <Text style={styles.coreTitle}>Client Intelligence{"\n"}Layer</Text>
          <View style={styles.nightly}>
            <Ionicons name="time-outline" size={11} color="rgba(255,255,255,0.55)" />
            <Text style={styles.nightlyText}>nightly job</Text>
          </View>
        </View>
        <LoopNode number="1" angle={-90} />
        <LoopNode number="2" angle={30} />
        <LoopNode number="3" angle={150} />
      </View>

      <View style={styles.callouts}>
        <Callout
          marker="1"
          title="Per-client learning"
          detail="Knows every client better every day"
        />
        <Callout
          marker="2"
          title="Cross-client patterns"
          detail="Every client benefits from patterns across the book — fully anonymized"
        />
        <Callout marker="3" title="System outcomes" detail="Measurably better every week it runs" />
        <Callout
          marker="✓"
          title="Provenance"
          detail="Every fact has a source, a timestamp, and an audit trail"
        />
      </View>

      <View style={styles.roadmap}>
        <Text style={styles.roadmapHeader}>PATH TO PRODUCTION</Text>
        <View style={styles.roadmapRow}>
          <RoadmapStep label="Demo" today />
          <RoadmapStep label="LLM chat" />
          <RoadmapStep label="Real data" />
          <RoadmapStep label="Briefs" />
          <RoadmapStep label="Memory" />
          <RoadmapStep label="Production" last />
        </View>
      </View>

      <Text style={styles.closing}>
        Models are rented. This memory is owned — and it compounds.
      </Text>
    </View>
  );
}

function LoopNode({ number, angle }: { number: string; angle: number }) {
  const radians = (angle * Math.PI) / 180;
  return (
    <View
      style={[
        styles.loopNode,
        {
          transform: [
            { translateX: 130 * Math.cos(radians) },
            { translateY: 130 * Math.sin(radians) },
          ],
        },
      ]}
    >
      <Text style={styles.loopNodeText}>{number}</Text>
    </View>
  );
}

function RoadmapStep({ label, today, last }: { label: string; today?: boolean; last?: boolean }) {
  return (
    <View style={styles.roadmapStep}>
      <View style={[styles.roadmapChip, today && styles.roadmapChipToday]}>
        <Text style={[styles.roadmapChipText, today && styles.roadmapChipTextToday]}>{label}</Text>
      </View>
      {!last ? <Ionicons name="chevron-forward" size={10} color="rgba(255,255,255,0.35)" /> : null}
    </View>
  );
}

function Callout({ marker, title, detail }: { marker: string; title: string; detail: string }) {
  return (
    <View style={styles.callout}>
      <View style={styles.calloutMarker}>
        <Text style={styles.calloutMarkerText}>{marker}</Text>
      </View>
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={styles.calloutTitle}>{title}</Text>
        <Text style={styles.calloutDetail}>{detail}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.allworthNavy, justifyContent: "space-between" },
  subtitle: { fontSize: 15, fontFamily: fonts.sans, color: "rgba(255,255,255,0.6)", marginTop: 10 },
  diagram: { height: 290, alignItems: "center", justifyContent: "center" },
  dashedCircle: {
    position: "absolute",
    width: 260,
    height: 260,
    borderRadius: 130,
    borderWidth: 1,
    borderStyle: "dashed",
    borderColor: "rgba(255,255,255,0.18)",
  },
  core: {
    width: 150,
    height: 150,
    borderRadius: 75,
    backgroundColor: "rgba(255,255,255,0.08)",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
  },
  coreTitle: { fontSize: 15, fontFamily: fonts.sansBold, color: "#fff", textAlign: "center" },
  nightly: { flexDirection: "row", alignItems: "center", gap: 4 },
  nightlyText: { fontSize: 11, fontFamily: fonts.sans, color: "rgba(255,255,255,0.55)" },
  loopNode: {
    position: "absolute",
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: "#fff",
    alignItems: "center",
    justifyContent: "center",
  },
  loopNodeText: { fontSize: 15, fontFamily: fonts.sansBold, color: colors.allworthNavy },
  roadmap: { paddingHorizontal: 24, gap: 8, alignItems: "center" },
  roadmapHeader: {
    fontSize: 10,
    fontFamily: fonts.sansBold,
    letterSpacing: 1.2,
    color: "rgba(255,255,255,0.45)",
  },
  roadmapRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    flexWrap: "wrap",
  },
  roadmapStep: { flexDirection: "row", alignItems: "center", gap: 2, marginRight: 2 },
  roadmapChip: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.25)",
  },
  roadmapChipToday: { backgroundColor: "#fff", borderColor: "#fff" },
  roadmapChipText: { fontSize: 11, fontFamily: fonts.sansBold, color: "rgba(255,255,255,0.75)" },
  roadmapChipTextToday: { color: colors.allworthNavy },
  callouts: { paddingHorizontal: 32, gap: 16 },
  callout: { flexDirection: "row", gap: 12, alignItems: "flex-start" },
  calloutMarker: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: "#fff",
    alignItems: "center",
    justifyContent: "center",
  },
  calloutMarkerText: { fontSize: 13, fontFamily: fonts.sansBold, color: colors.allworthNavy },
  calloutTitle: { fontSize: 15, fontFamily: fonts.sansBold, color: "#fff" },
  calloutDetail: { fontSize: 13, fontFamily: fonts.sans, color: "rgba(255,255,255,0.65)" },
  // Playfair italic — same treatment as the brand tagline "You get a financial ally for life."
  closing: {
    fontSize: 19,
    fontFamily: fonts.displayItalic,
    color: "#fff",
    textAlign: "center",
    paddingHorizontal: 40,
  },
});
