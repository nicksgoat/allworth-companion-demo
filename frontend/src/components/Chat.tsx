import { Ionicons } from "@expo/vector-icons";
import React, { useEffect, useMemo, useRef, useState } from "react";
import type { TextStyle } from "react-native";
import { Animated, Easing, Platform, Pressable, StyleSheet, Text, View } from "react-native";
import { FadeScaleIn, useAnimatedValue, usePulse } from "../anim";
import { colors, fonts, radius, space, text } from "../theme";
import type { ChatMessage, ToolChip } from "../types";
import { AdvisorHandoffCard } from "./AdvisorHandoffCard";
import { ChatToolWidget } from "./ChatToolWidget";
import { AllworthMark } from "./Wordmark";

export function ToolChipRow({
  chips,
  sources,
  collapsed,
}: {
  chips: ToolChip[];
  sources: string[];
  collapsed: boolean;
}) {
  if (collapsed && sources.length > 0) {
    return (
      <View style={styles.sourcesRow}>
        <Ionicons name="search-outline" size={12} color={colors.inkTertiary} />
        <Text style={styles.sourcesText}>Sources: {sources.join(" · ")}</Text>
      </View>
    );
  }
  if (!collapsed && chips.length > 0) {
    return (
      <View style={styles.chipFlow}>
        {chips.map((chip) => (
          <ToolChipView key={chip.name} chip={chip} />
        ))}
      </View>
    );
  }
  return null;
}

// A softly pulsing dot reads as deliberate "thinking" — calmer and more premium
// than a spinner. Each chip also fades + scales in as the step begins.
function ThinkingDot() {
  const pulse = usePulse(0.3, 1, 620);
  return <Animated.View style={[styles.thinkingDot, { opacity: pulse }]} />;
}

function ToolChipView({ chip }: { chip: ToolChip }) {
  return (
    <FadeScaleIn>
      <View style={styles.chip}>
        {chip.running ? (
          <ThinkingDot />
        ) : (
          <Ionicons name="checkmark" size={11} color={colors.allworthAccent} />
        )}
        <Text style={styles.chipText}>{chip.label}</Text>
      </View>
    </FadeScaleIn>
  );
}

// Blinking caret while the answer streams in.
function TypingCursor() {
  const blink = usePulse(0.15, 1, 520);
  return <Animated.Text style={{ color: colors.inkTertiary, opacity: blink }}> ▍</Animated.Text>;
}

// Inline **bold** rendering that tolerates a half-streamed token: a trailing,
// not-yet-closed "**" renders its tail bold rather than flashing the asterisks.
function renderBold(text: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  let i = 0;
  let key = 0;
  while (i < text.length) {
    const open = text.indexOf("**", i);
    if (open === -1) {
      out.push(<Text key={key++}>{text.slice(i)}</Text>);
      break;
    }
    if (open > i) out.push(<Text key={key++}>{text.slice(i, open)}</Text>);
    const close = text.indexOf("**", open + 2);
    if (close === -1) {
      // Bold opened but not yet closed (still revealing) — render tail bold, no markers.
      out.push(
        <Text key={key++} style={{ fontFamily: fonts.sansBold }}>
          {text.slice(open + 2)}
        </Text>,
      );
      break;
    }
    out.push(
      <Text key={key++} style={{ fontFamily: fonts.sansBold }}>
        {text.slice(open + 2, close)}
      </Text>,
    );
    i = close + 2;
  }
  return out;
}

// Lightweight block markdown: GPT-4o answers use #/##/### headings, --- rules,
// and "- " bullets. Rendering the raw text leaked those markers on screen, so we
// parse line-by-line into blocks — headings become bold section headers, rules
// become a hairline divider, bullets get a real glyph — while inline **bold**
// and the streaming cursor are preserved. Tolerant of half-streamed lines: a
// line that is just "##" briefly renders as an (empty) heading until its text
// arrives, never as a literal marker.
type MdBlock =
  | { kind: "heading"; text: string }
  | { kind: "rule" }
  | { kind: "bullet"; text: string }
  | { kind: "para"; text: string };

function parseBlocks(src: string): MdBlock[] {
  const blocks: MdBlock[] = [];
  for (const raw of src.split("\n")) {
    const line = raw.replace(/\s+$/, "");
    if (!line.trim()) continue; // blank lines become block spacing (gap)
    if (/^\s*([-*_])\1{2,}\s*$/.test(line)) {
      blocks.push({ kind: "rule" });
    } else if (/^\s*#{1,6}/.test(line)) {
      blocks.push({ kind: "heading", text: line.replace(/^\s*#{1,6}\s*/, "") });
    } else if (/^\s*[-*]\s+/.test(line)) {
      blocks.push({ kind: "bullet", text: line.replace(/^\s*[-*]\s+/, "") });
    } else {
      blocks.push({ kind: "para", text: line });
    }
  }
  return blocks;
}

function MarkdownText({ text, streaming }: { text: string; streaming: boolean }) {
  const blocks = parseBlocks(text);
  return (
    <View style={styles.markdown}>
      {blocks.map((block, i) => {
        const cursor = streaming && i === blocks.length - 1 ? <TypingCursor /> : null;
        if (block.kind === "rule") return <View key={i} style={styles.mdRule} />;
        if (block.kind === "heading") {
          return (
            <Text key={i} style={[styles.mdHeading, webTextWrap]}>
              {renderBold(block.text)}
              {cursor}
            </Text>
          );
        }
        if (block.kind === "bullet") {
          return (
            <View key={i} style={styles.mdBulletRow}>
              <Text style={[styles.assistantText, styles.mdBullet]}>•</Text>
              <Text style={[styles.assistantText, webTextWrap, styles.mdBulletText]}>
                {renderBold(block.text)}
                {cursor}
              </Text>
            </View>
          );
        }
        return (
          <Text key={i} style={[styles.assistantText, webTextWrap]}>
            {renderBold(block.text)}
            {cursor}
          </Text>
        );
      })}
    </View>
  );
}

function AssistantIdentity() {
  return (
    <View style={styles.identityRow}>
      <View style={styles.avatar}>
        <AllworthMark size={14} color="#FFFFFF" />
      </View>
      <Text style={styles.identityName}>Allworth Assistant</Text>
    </View>
  );
}

// ── Word-fade reveal ────────────────────────────────────────────────────────
// The whole received answer is laid out immediately; unrevealed words sit at
// opacity 0, so they reserve their final position and revealed text never reflows
// or jumps a line. A read-head sweeps left-to-right at a constant chars/sec and
// each word it passes fades from 0→1 (native-driver opacity, off the JS thread).
const REVEAL_CPS = 260; // read-head speed — calm, deliberate, even
const FADE_MS = 240; // per-word fade duration

// One renderable unit: a word (with bold flag) or a horizontal rule. `start` is
// the unit's offset in visible-char space; `idx` is its document order.
type AWord = { kind: "word"; text: string; bold: boolean; idx: number; start: number };
type ABlock =
  | { kind: "heading" | "para" | "bullet"; words: AWord[] }
  | { kind: "rule"; idx: number; start: number };
type Parsed = { blocks: ABlock[]; starts: number[]; totalUnits: number; totalChars: number };

// Strip ** markers, returning the clean text plus a per-char "is bold" map so each
// word can recover its weight after the markers are gone.
function stripBold(content: string): { clean: string; boldAt: boolean[] } {
  let clean = "";
  const boldAt: boolean[] = [];
  let bold = false;
  for (let i = 0; i < content.length; i++) {
    if (content[i] === "*" && content[i + 1] === "*") {
      bold = !bold;
      i++;
      continue;
    }
    clean += content[i];
    boldAt.push(bold);
  }
  return { clean, boldAt };
}

function tokenizeAnswer(full: string): Parsed {
  const blocks: ABlock[] = [];
  const starts: number[] = [];
  let idx = 0;
  let charPos = 0;
  for (const raw of full.split("\n")) {
    const line = raw.replace(/\s+$/, "");
    if (!line.trim()) continue;
    if (/^\s*([-*_])\1{2,}\s*$/.test(line)) {
      blocks.push({ kind: "rule", idx, start: charPos });
      starts.push(charPos);
      idx++;
      charPos += 1;
      continue;
    }
    let kind: "heading" | "para" | "bullet" = "para";
    let content = line;
    if (/^\s*#{1,6}/.test(line)) {
      kind = "heading";
      content = line.replace(/^\s*#{1,6}\s*/, "");
    } else if (/^\s*[-*]\s+/.test(line)) {
      kind = "bullet";
      content = line.replace(/^\s*[-*]\s+/, "");
    }
    const { clean, boldAt } = stripBold(content);
    const base = charPos;
    const words: AWord[] = [];
    const re = /\S+\s*/g; // a word plus its trailing whitespace
    let m: RegExpExecArray | null;
    while ((m = re.exec(clean)) !== null) {
      const start = base + m.index;
      words.push({ kind: "word", text: m[0], bold: boldAt[m.index] ?? false, idx, start });
      starts.push(start);
      idx++;
    }
    charPos = base + clean.length + 1; // +1 stands in for the line break
    blocks.push({ kind, words });
  }
  return { blocks, starts, totalUnits: idx, totalChars: charPos };
}

// Advance a read-head at a constant rate and return how many units it has passed.
// State updates only when that count changes (≈ once per word), not every frame.
function useWordReveal(parsed: Parsed, streaming: boolean, animate: boolean): number {
  const [count, setCount] = useState(animate ? 0 : parsed.totalUnits);
  const startsRef = useRef(parsed.starts);
  const totalRef = useRef(parsed.totalChars);
  const streamingRef = useRef(streaming);
  const countRef = useRef(count);
  const headRef = useRef(0);
  const lastTsRef = useRef(0);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    startsRef.current = parsed.starts;
    totalRef.current = parsed.totalChars;
    streamingRef.current = streaming;
  });

  useEffect(() => {
    if (!animate) {
      countRef.current = startsRef.current.length;
      setCount(startsRef.current.length);
      return;
    }
    const tick = (ts: number) => {
      if (lastTsRef.current === 0) lastTsRef.current = ts;
      const dt = Math.min(64, ts - lastTsRef.current); // clamp gaps (backgrounding)
      lastTsRef.current = ts;
      headRef.current = Math.min(totalRef.current, headRef.current + (REVEAL_CPS * dt) / 1000);
      const s = startsRef.current;
      let c = countRef.current;
      while (c < s.length && s[c] <= headRef.current) c++;
      if (c !== countRef.current) {
        countRef.current = c;
        setCount(c);
      }
      if (headRef.current < totalRef.current || streamingRef.current) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        rafRef.current = null; // fully revealed and the stream has ended — stop
      }
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    };
  }, [animate]);

  return count;
}

// A single word, laid out from birth, that fades in once when the read-head reaches
// it. Memoized so a reveal step only re-renders the one word whose flag flipped.
const FadeWord = React.memo(function FadeWord({
  text,
  bold,
  revealed,
  textStyle,
}: {
  text: string;
  bold: boolean;
  revealed: boolean;
  textStyle: TextStyle;
}) {
  const op = useAnimatedValue(revealed ? 1 : 0);
  const faded = useRef(revealed);
  useEffect(() => {
    if (revealed && !faded.current) {
      faded.current = true;
      Animated.timing(op, {
        toValue: 1,
        duration: FADE_MS,
        easing: Easing.out(Easing.quad),
        useNativeDriver: true,
      }).start();
    }
  }, [revealed, op]);
  return (
    <Animated.View style={{ opacity: op }}>
      <Text style={[textStyle, bold ? styles.fadeBold : null]}>{text}</Text>
    </Animated.View>
  );
});

function FadeAnswer({ parsed, revealedCount }: { parsed: Parsed; revealedCount: number }) {
  return (
    <View style={styles.markdown}>
      {parsed.blocks.map((block, bi) => {
        if (block.kind === "rule") {
          return (
            <View
              key={bi}
              style={[styles.mdRule, { opacity: block.idx < revealedCount ? 1 : 0 }]}
            />
          );
        }
        const textStyle = block.kind === "heading" ? styles.mdHeading : styles.assistantText;
        const firstRevealed = (block.words[0]?.idx ?? Infinity) < revealedCount;
        return (
          <View key={bi} style={styles.fadeRow}>
            {block.kind === "bullet" ? (
              <FadeWord text="•  " bold={false} revealed={firstRevealed} textStyle={textStyle} />
            ) : null}
            {block.words.map((w) => (
              <FadeWord
                key={w.idx}
                text={w.text}
                bold={w.bold}
                revealed={w.idx < revealedCount}
                textStyle={textStyle}
              />
            ))}
          </View>
        );
      })}
    </View>
  );
}

type ChatMessageViewProps = {
  message: ChatMessage;
  // Only the first assistant message in a consecutive run shows the identity row,
  // so a thread reads as one continuing voice rather than a repeating header.
  showIdentity?: boolean;
  onFeedback?: (message: ChatMessage, rating: "positive" | "negative") => void;
  handoffDisabled?: boolean;
  // Fired once an answer has fully typed in — lets the parent hold follow-up
  // suggestion chips until the reveal finishes, not when the stream ends.
  onRevealed?: (id: string) => void;
};

function ChatMessageViewImpl(props: ChatMessageViewProps) {
  if (props.message.role === "user") {
    return (
      <View style={styles.userRow}>
        <View style={styles.userBubble}>
          <Text style={[styles.userText, webTextWrap]}>{props.message.text}</Text>
        </View>
      </View>
    );
  }
  return <AssistantBubble {...props} />;
}

function AssistantBubble({
  message,
  showIdentity = true,
  onFeedback,
  handoffDisabled,
  onRevealed,
}: ChatMessageViewProps) {
  // A message fades in only if it was streaming when it first mounted (the live
  // answer), so the greeting / restored history appear instantly. Captured once.
  const [animate] = useState(message.isStreaming);
  const parsed = useMemo(() => tokenizeAnswer(message.text), [message.text]);
  const revealedCount = useWordReveal(parsed, message.isStreaming, animate);
  const typing = animate && (revealedCount < parsed.totalUnits || message.isStreaming);

  // Once the answer has fully revealed, let the parent reveal follow-up chips.
  useEffect(() => {
    if (!typing && message.text) onRevealed?.(message.id);
  }, [typing, message.text, message.id, onRevealed]);

  // "Done" means fully typed in — the feedback thumbs and advisor handoff appear after
  // the reveal completes, not mid-type.
  const done = !message.isStreaming && !typing;
  // One subtle action row at the foot of a finished answer: ghost thumbs on the
  // left, the compact advisor handoff on the right — no labels, no extra card.
  const showHandoff = done && message.sources.length > 0;
  const showFeedback = done && !!message.text;

  return (
    <View style={styles.assistantBlock}>
      {showIdentity ? <AssistantIdentity /> : null}
      <ToolChipRow
        chips={message.chips}
        sources={message.sources}
        collapsed={!message.isStreaming}
      />
      {message.widgets?.map((w, i) => (
        <ChatToolWidget key={`${w.name}-${i}`} widget={w} />
      ))}
      {message.text ? (
        animate ? (
          <FadeAnswer parsed={parsed} revealedCount={revealedCount} />
        ) : (
          <MarkdownText text={message.text} streaming={false} />
        )
      ) : null}
      {showHandoff || showFeedback ? (
        <View style={styles.actionRow}>
          {showFeedback ? (
            <View style={styles.feedbackRow}>
              <Pressable
                hitSlop={8}
                onPress={() => onFeedback?.(message, "positive")}
                style={({ pressed }) => [styles.feedbackButton, pressed && { opacity: 0.6 }]}
              >
                <Ionicons
                  name={message.feedback === "positive" ? "thumbs-up" : "thumbs-up-outline"}
                  size={15}
                  color={
                    message.feedback === "positive" ? colors.allworthAccent : colors.inkTertiary
                  }
                />
              </Pressable>
              <Pressable
                hitSlop={8}
                onPress={() => onFeedback?.(message, "negative")}
                style={({ pressed }) => [styles.feedbackButton, pressed && { opacity: 0.6 }]}
              >
                <Ionicons
                  name={message.feedback === "negative" ? "thumbs-down" : "thumbs-down-outline"}
                  size={15}
                  color={
                    message.feedback === "negative" ? colors.allworthAccent : colors.inkTertiary
                  }
                />
              </Pressable>
            </View>
          ) : null}
          {showHandoff ? (
            <View style={styles.handoffSlot}>
              <AdvisorHandoffCard compact disabled={handoffDisabled} />
            </View>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

// Memoized so a streaming answer only re-renders its own bubble, not the whole
// thread. Every token flush replaces the streaming message by reference while
// finished messages keep their identity, so reference equality on `message` is
// the right gate. Function props are intentionally excluded from the compare:
// they change identity each parent render but behave identically, and any bubble
// that genuinely needs fresh handlers (a new turn, or `sending`/handoffDisabled
// toggling at send boundaries) re-renders on those props anyway.
export const ChatMessageView = React.memo(
  ChatMessageViewImpl,
  (prev, next) =>
    prev.message === next.message &&
    prev.showIdentity === next.showIdentity &&
    prev.handoffDisabled === next.handoffDisabled,
);

const webTextWrap =
  Platform.OS === "web"
    ? ({
        whiteSpace: "pre-wrap",
        overflowWrap: "break-word",
        wordBreak: "break-word",
      } as any)
    : null;

const styles = StyleSheet.create({
  sourcesRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  sourcesText: {
    ...text.bodySm,
    color: colors.inkTertiary,
    flex: 1,
    flexShrink: 1,
    minWidth: 0,
  },
  chipFlow: { flexDirection: "row", flexWrap: "wrap", gap: space[2] },
  chip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: space[3],
    paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: colors.inkFaint,
  },
  chipText: { ...text.bodySm, color: colors.inkSecondary },
  thinkingDot: { width: 7, height: 7, borderRadius: 3.5, backgroundColor: colors.allworthAccent },
  userRow: { flexDirection: "row", justifyContent: "flex-end", paddingLeft: 48, maxWidth: "100%" },
  userBubble: {
    backgroundColor: colors.inkFaint,
    borderRadius: 16,
    paddingHorizontal: 14,
    paddingVertical: 10,
    maxWidth: "100%",
    flexShrink: 1,
  },
  userText: {
    fontSize: 17,
    fontFamily: fonts.sans,
    color: colors.inkPrimary,
    flexShrink: 1,
    minWidth: 0,
  },
  assistantBlock: {
    gap: space[3],
    alignSelf: "stretch",
    maxWidth: "100%",
    flexShrink: 1,
    minWidth: 0,
  },
  assistantText: {
    fontSize: 17,
    fontFamily: fonts.sans,
    color: colors.inkPrimary,
    lineHeight: 24,
    alignSelf: "stretch",
    maxWidth: "100%",
    flexShrink: 1,
    minWidth: 0,
  },
  // Block markdown: paragraphs/headings/bullets/rules stack with even spacing.
  markdown: { alignSelf: "stretch", maxWidth: "100%", flexShrink: 1, minWidth: 0, gap: space[2] },
  mdHeading: {
    fontSize: 17,
    fontFamily: fonts.sansBold,
    color: colors.inkPrimary,
    lineHeight: 24,
    marginTop: space[1],
    alignSelf: "stretch",
    maxWidth: "100%",
    flexShrink: 1,
    minWidth: 0,
  },
  mdRule: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: colors.hairline,
    alignSelf: "stretch",
  },
  mdBulletRow: { flexDirection: "row", gap: space[2], alignSelf: "stretch", maxWidth: "100%" },
  mdBullet: { color: colors.inkSecondary },
  mdBulletText: { flex: 1 },
  // Word-fade reveal: words flow + wrap like text, each fading in over the layout.
  fadeRow: { flexDirection: "row", flexWrap: "wrap", alignSelf: "stretch", maxWidth: "100%" },
  fadeBold: { fontFamily: fonts.sansBold },
  identityRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  avatar: {
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: colors.allworthNavy,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarText: { fontSize: 12, fontFamily: fonts.sansBold, color: "#FFFFFF" },
  identityName: { fontSize: 13, fontFamily: fonts.sansBold, color: colors.inkSecondary },
  // The single foot-of-answer action row: ghost thumbs + compact handoff.
  actionRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: space[3],
    paddingTop: space[1],
  },
  feedbackRow: { flexDirection: "row", alignItems: "center", gap: space[3] },
  feedbackButton: { alignItems: "center", justifyContent: "center" },
  handoffSlot: { flexShrink: 1, alignItems: "flex-end" },
});
