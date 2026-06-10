import React, { useMemo, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View
} from "react-native";
import { StatusBar } from "expo-status-bar";
import { Ionicons } from "@expo/vector-icons";

import { ChatMessage, ChatResponse, sendChat } from "./src/api";
import {
  defaultHousehold,
  defaultPortfolio,
  formatCurrency,
  largestDrift,
  portfolioTotal,
  updateHouseholdField
} from "./src/lib/planningLogic.mjs";

type Screen = "chat" | "goals" | "portfolio" | "advisor";

const advisor = {
  initials: "DW",
  name: "Dana Williams",
  title: "Senior Financial Advisor, CFP®"
};

const concentration = {
  symbol: "NVDA",
  company: "NVIDIA Corp.",
  value: 52080,
  accountName: "Robinhood",
  percent: 0.54
};

const starterPrompts = [
  "What should I do first?",
  "Show tax-aware options",
  "Can I retire at 62?",
  "Review my portfolio drift"
];

const goals = [
  { name: "Retirement", target: 2200000, current: 1250000, date: "2045", tone: "#007a5a" },
  { name: "Emergency Reserve", target: 90000, current: 64000, date: "2027", tone: "#2d7ff9" },
  { name: "Taxable Opportunity", target: 120000, current: 52080, date: "This year", tone: "#c9780f" }
];

export default function App() {
  const [screen, setScreen] = useState<Screen>("chat");
  const [household, setHousehold] = useState(defaultHousehold);
  const [portfolio] = useState(defaultPortfolio);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content:
        "Good morning. I found one item worth reviewing: NVDA is about 54% of your Robinhood account. I can compare diversification paths, tax impact, and timing."
    }
  ]);
  const [draft, setDraft] = useState("");
  const [latest, setLatest] = useState<ChatResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const total = useMemo(() => portfolioTotal(portfolio), [portfolio]);
  const drift = useMemo(() => largestDrift(portfolio), [portfolio]);
  const accountTotal = total + concentration.value;
  const percentText = Math.round(concentration.percent * 100);
  const fundedPercent = goals[0].current / goals[0].target;

  async function submitPrompt(prompt = draft) {
    const trimmed = prompt.trim();
    if (!trimmed || loading) return;

    const nextMessages: ChatMessage[] = [...messages, { role: "user", content: trimmed }];
    setMessages(nextMessages);
    setDraft("");
    setError("");
    setLoading(true);
    setScreen("chat");

    try {
      const response = await sendChat(nextMessages, household, portfolio);
      setLatest(response);
      setMessages([...nextMessages, { role: "assistant", content: response.answer }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="dark" />
      <KeyboardAvoidingView style={styles.app} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <View style={styles.header}>
          <View>
            <Text style={styles.kicker}>Allworth Invest</Text>
            <Text style={styles.title}>{screenTitle(screen)}</Text>
          </View>
          <Pressable style={styles.profileButton} onPress={() => setScreen("advisor")}>
            <Text style={styles.profileText}>{advisor.initials}</Text>
          </Pressable>
        </View>

        {screen === "chat" && (
          <View style={styles.chatScreen}>
            <ScrollView style={styles.mainScroll} contentContainerStyle={styles.chatContent} showsVerticalScrollIndicator={false}>
              <View style={styles.balancePanel}>
                <Text style={styles.panelLabel}>Total invested assets</Text>
                <Text style={styles.balanceValue}>{formatCurrency(accountTotal)}</Text>
                <View style={styles.balanceMetaRow}>
                  <Pill icon="trending-up" label="On track" color="#007a5a" />
                  <Text style={styles.mutedText}>{Math.round(fundedPercent * 100)}% funded for retirement</Text>
                </View>
              </View>

              <View style={styles.insightPanel}>
                <View style={styles.insightIcon}>
                  <Ionicons name="alert-circle" size={23} color="#fff" />
                </View>
                <View style={styles.insightCopy}>
                  <Text style={styles.insightTitle}>{concentration.symbol} is a large share of one account</Text>
                  <Text style={styles.insightBody}>
                    {concentration.company} is about {percentText}% of your {concentration.accountName} account ({formatCurrency(concentration.value)}).
                  </Text>
                </View>
              </View>

              <Text style={styles.sectionTitle}>Ask your planner</Text>
              <View style={styles.promptGrid}>
                {starterPrompts.map((prompt) => (
                  <Pressable key={prompt} style={styles.promptCard} onPress={() => submitPrompt(prompt)}>
                    <Text style={styles.promptCardText}>{prompt}</Text>
                  </Pressable>
                ))}
              </View>

              <View style={styles.thread}>
                {messages.map((message, index) => (
                  <View key={`${message.role}-${index}`} style={[styles.bubble, message.role === "user" ? styles.userBubble : styles.assistantBubble]}>
                    <Text style={[styles.bubbleText, message.role === "user" ? styles.userText : styles.assistantText]}>{message.content}</Text>
                  </View>
                ))}
                {latest?.result.cards?.length ? (
                  <View style={styles.resultCards}>
                    {latest.result.cards.map((card) => (
                      <View key={card.label} style={styles.resultCard}>
                        <Text style={styles.resultLabel}>{card.label}</Text>
                        <Text style={styles.resultValue}>{card.value}</Text>
                        {!!card.detail && <Text style={styles.resultDetail}>{card.detail}</Text>}
                      </View>
                    ))}
                  </View>
                ) : null}
                {loading && <ActivityIndicator color="#007a5a" />}
                {!!error && <Text style={styles.error}>{error}</Text>}
              </View>
            </ScrollView>

            <View style={styles.composer}>
              <TextInput value={draft} onChangeText={setDraft} placeholder="Ask about your money" placeholderTextColor="#7b827c" style={styles.input} multiline />
              <Pressable style={styles.sendButton} onPress={() => submitPrompt()}>
                <Ionicons name="arrow-up" size={22} color="#fff" />
              </Pressable>
            </View>
          </View>
        )}

        {screen === "goals" && (
          <ScrollView style={styles.mainScroll} contentContainerStyle={styles.pageContent} showsVerticalScrollIndicator={false}>
            <View style={styles.heroCard}>
              <Text style={styles.panelLabel}>Retirement readiness</Text>
              <Text style={styles.heroNumber}>{Math.round(fundedPercent * 100)}%</Text>
              <Progress value={fundedPercent} color="#007a5a" />
              <Text style={styles.heroCopy}>You are tracking toward retirement at {household.retirement_age}. Raising annual savings could improve the margin.</Text>
            </View>

            <Text style={styles.sectionTitle}>Goals</Text>
            {goals.map((goal) => (
              <View key={goal.name} style={styles.goalCard}>
                <View style={styles.cardHeader}>
                  <View>
                    <Text style={styles.cardTitle}>{goal.name}</Text>
                    <Text style={styles.cardSubtitle}>Target {goal.date}</Text>
                  </View>
                  <Text style={styles.cardValue}>{Math.round((goal.current / goal.target) * 100)}%</Text>
                </View>
                <Progress value={goal.current / goal.target} color={goal.tone} />
                <View style={styles.cardFooter}>
                  <Text style={styles.mutedText}>{formatCurrency(goal.current)}</Text>
                  <Text style={styles.mutedText}>{formatCurrency(goal.target)}</Text>
                </View>
              </View>
            ))}

            <Text style={styles.sectionTitle}>Household</Text>
            <View style={styles.formCard}>
              <Field label="Retirement age" value={String(household.retirement_age)} onChange={(value) => setHousehold(updateHouseholdField(household, "retirement_age", value))} />
              <Field label="Annual income" value={String(household.annual_income)} onChange={(value) => setHousehold(updateHouseholdField(household, "annual_income", value))} />
              <Field label="Annual savings" value={String(household.annual_savings)} onChange={(value) => setHousehold(updateHouseholdField(household, "annual_savings", value))} last />
            </View>
          </ScrollView>
        )}

        {screen === "portfolio" && (
          <ScrollView style={styles.mainScroll} contentContainerStyle={styles.pageContent} showsVerticalScrollIndicator={false}>
            <View style={styles.heroCard}>
              <Text style={styles.panelLabel}>Portfolio value</Text>
              <Text style={styles.balanceValue}>{formatCurrency(total)}</Text>
              <View style={styles.balanceMetaRow}>
                <Pill icon="pie-chart" label={`${portfolio.length} holdings`} color="#2d7ff9" />
                <Text style={styles.mutedText}>Largest drift {(drift * 100).toFixed(1)}%</Text>
              </View>
            </View>

            <Text style={styles.sectionTitle}>Allocation</Text>
            <View style={styles.formCard}>
              {portfolio.map((position, index) => {
                const weight = position.value / total;
                return (
                  <View key={position.symbol} style={[styles.allocationRow, index === portfolio.length - 1 && styles.lastRow]}>
                    <View style={styles.allocationTop}>
                      <View>
                        <Text style={styles.cardTitle}>{position.symbol}</Text>
                        <Text style={styles.cardSubtitle}>{position.name}</Text>
                      </View>
                      <Text style={styles.cardValue}>{Math.round(weight * 100)}%</Text>
                    </View>
                    <Progress value={weight} color={index === 0 ? "#007a5a" : index === 1 ? "#2d7ff9" : index === 2 ? "#667085" : "#c9780f"} />
                    <Text style={styles.mutedText}>{formatCurrency(position.value)}</Text>
                  </View>
                );
              })}
            </View>

            <Text style={styles.sectionTitle}>Recommendations</Text>
            <ActionCard icon="leaf" title="Harvest losses" detail="VXUS has an unrealized loss that may offset taxable gains." />
            <ActionCard icon="swap-horizontal" title="Rebalance gradually" detail="Move excess single-stock risk into diversified targets over time." />
          </ScrollView>
        )}

        {screen === "advisor" && (
          <ScrollView style={styles.mainScroll} contentContainerStyle={styles.pageContent} showsVerticalScrollIndicator={false}>
            <View style={styles.advisorHero}>
              <View style={styles.largeAvatar}>
                <Text style={styles.largeAvatarText}>{advisor.initials}</Text>
              </View>
              <Text style={styles.advisorName}>{advisor.name}</Text>
              <Text style={styles.advisorTitle}>{advisor.title}</Text>
              <View style={styles.advisorActions}>
                <Pressable style={styles.actionButton} onPress={() => submitPrompt("Prepare a message to my advisor about NVDA concentration.")}>
                  <Ionicons name="chatbubble" size={19} color="#fff" />
                  <Text style={styles.actionButtonText}>Message</Text>
                </Pressable>
                <Pressable style={[styles.actionButton, styles.secondaryButton]}>
                  <Ionicons name="calendar" size={19} color="#007a5a" />
                  <Text style={[styles.actionButtonText, styles.secondaryButtonText]}>Schedule</Text>
                </Pressable>
              </View>
            </View>

            <Text style={styles.sectionTitle}>Advisor brief</Text>
            <ActionCard icon="alert-circle" title={`${concentration.symbol} concentration`} detail={`${percentText}% of ${concentration.accountName}; review tax-aware diversification paths.`} />
            <ActionCard icon="checkmark-circle" title="Retirement remains on track" detail={`Current plan shows ${Math.round(fundedPercent * 100)}% funded toward the retirement target.`} />
          </ScrollView>
        )}

        <View style={styles.tabBar}>
          <TabButton active={screen === "chat"} icon="chatbubble-ellipses" label="Chat" onPress={() => setScreen("chat")} />
          <TabButton active={screen === "goals"} icon="flag" label="Goals" onPress={() => setScreen("goals")} />
          <TabButton active={screen === "portfolio"} icon="pie-chart" label="Portfolio" onPress={() => setScreen("portfolio")} />
          <TabButton active={screen === "advisor"} icon="person-circle" label="Advisor" onPress={() => setScreen("advisor")} />
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function screenTitle(screen: Screen) {
  if (screen === "chat") return "Chat";
  if (screen === "goals") return "Goals";
  if (screen === "portfolio") return "Portfolio";
  return "Advisor";
}

function Pill({ icon, label, color }: { icon: keyof typeof Ionicons.glyphMap; label: string; color: string }) {
  return (
    <View style={[styles.pill, { backgroundColor: `${color}18` }]}>
      <Ionicons name={icon} size={14} color={color} />
      <Text style={[styles.pillText, { color }]}>{label}</Text>
    </View>
  );
}

function Progress({ value, color }: { value: number; color: string }) {
  const width = `${Math.max(4, Math.min(100, value * 100))}%` as `${number}%`;
  return (
    <View style={styles.progressTrack}>
      <View style={[styles.progressFill, { width, backgroundColor: color }]} />
    </View>
  );
}

function Field({ label, value, onChange, last }: { label: string; value: string; onChange: (value: string) => void; last?: boolean }) {
  return (
    <View style={[styles.fieldRow, last && styles.lastRow]}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput value={value} onChangeText={onChange} keyboardType="numeric" style={styles.fieldInput} />
    </View>
  );
}

function ActionCard({ icon, title, detail }: { icon: keyof typeof Ionicons.glyphMap; title: string; detail: string }) {
  return (
    <View style={styles.actionCard}>
      <View style={styles.actionIcon}>
        <Ionicons name={icon} size={20} color="#007a5a" />
      </View>
      <View style={styles.actionCopy}>
        <Text style={styles.cardTitle}>{title}</Text>
        <Text style={styles.cardSubtitle}>{detail}</Text>
      </View>
      <Ionicons name="chevron-forward" size={18} color="#a9b0aa" />
    </View>
  );
}

function TabButton({ active, icon, label, onPress }: { active: boolean; icon: keyof typeof Ionicons.glyphMap; label: string; onPress: () => void }) {
  return (
    <Pressable style={styles.tabButton} onPress={onPress}>
      <Ionicons name={icon} size={22} color={active ? "#007a5a" : "#7b827c"} />
      <Text style={[styles.tabLabel, active && styles.tabLabelActive]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#f5f7f2" },
  app: { flex: 1, backgroundColor: "#f5f7f2" },
  header: { paddingHorizontal: 20, paddingTop: 12, paddingBottom: 10, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  kicker: { color: "#68746b", fontSize: 13, fontWeight: "700" },
  title: { color: "#0f1f17", fontSize: 34, lineHeight: 40, fontWeight: "800", letterSpacing: 0 },
  profileButton: { width: 42, height: 42, borderRadius: 21, backgroundColor: "#123d2d", alignItems: "center", justifyContent: "center" },
  profileText: { color: "#fff", fontSize: 15, fontWeight: "800" },
  chatScreen: { flex: 1 },
  mainScroll: { flex: 1 },
  chatContent: { paddingHorizontal: 16, paddingBottom: 12 },
  pageContent: { paddingHorizontal: 16, paddingBottom: 98 },
  balancePanel: { backgroundColor: "#123d2d", borderRadius: 8, padding: 18, marginBottom: 12 },
  panelLabel: { color: "#7b827c", fontSize: 12, fontWeight: "800", textTransform: "uppercase", letterSpacing: 1 },
  balanceValue: { color: "#0f1f17", fontSize: 38, lineHeight: 44, fontWeight: "800", letterSpacing: 0, marginTop: 8 },
  balanceMetaRow: { flexDirection: "row", alignItems: "center", gap: 10, marginTop: 14, flexWrap: "wrap" },
  mutedText: { color: "#6d766f", fontSize: 13, lineHeight: 18 },
  pill: { flexDirection: "row", alignItems: "center", gap: 5, borderRadius: 999, paddingHorizontal: 9, paddingVertical: 5 },
  pillText: { fontSize: 12, fontWeight: "800" },
  insightPanel: { backgroundColor: "#fff", borderRadius: 8, padding: 14, borderWidth: 1, borderColor: "#e1e6df", flexDirection: "row", gap: 12, marginBottom: 18 },
  insightIcon: { width: 42, height: 42, borderRadius: 21, backgroundColor: "#c9780f", alignItems: "center", justifyContent: "center" },
  insightCopy: { flex: 1 },
  insightTitle: { color: "#0f1f17", fontSize: 17, fontWeight: "800", lineHeight: 22 },
  insightBody: { color: "#566159", fontSize: 14, lineHeight: 20, marginTop: 4 },
  sectionTitle: { color: "#0f1f17", fontSize: 20, lineHeight: 25, fontWeight: "800", letterSpacing: 0, marginTop: 8, marginBottom: 10 },
  promptGrid: { flexDirection: "row", flexWrap: "wrap", gap: 9, marginBottom: 16 },
  promptCard: { width: "48.5%", minHeight: 72, backgroundColor: "#fff", borderRadius: 8, borderWidth: 1, borderColor: "#e1e6df", padding: 12, justifyContent: "center" },
  promptCardText: { color: "#123d2d", fontSize: 15, lineHeight: 20, fontWeight: "800" },
  thread: { gap: 10 },
  bubble: { maxWidth: "88%", borderRadius: 8, paddingHorizontal: 13, paddingVertical: 10 },
  userBubble: { alignSelf: "flex-end", backgroundColor: "#007a5a" },
  assistantBubble: { alignSelf: "flex-start", backgroundColor: "#fff", borderWidth: 1, borderColor: "#e1e6df" },
  bubbleText: { fontSize: 15, lineHeight: 21 },
  userText: { color: "#fff" },
  assistantText: { color: "#17231c" },
  resultCards: { gap: 8 },
  resultCard: { backgroundColor: "#fff", borderRadius: 8, borderWidth: 1, borderColor: "#e1e6df", padding: 12 },
  resultLabel: { color: "#68746b", fontSize: 12, fontWeight: "800", textTransform: "uppercase" },
  resultValue: { color: "#0f1f17", fontSize: 22, fontWeight: "800", marginTop: 3 },
  resultDetail: { color: "#566159", lineHeight: 19, marginTop: 4 },
  composer: { flexDirection: "row", alignItems: "flex-end", gap: 8, paddingHorizontal: 16, paddingTop: 8, paddingBottom: 10, backgroundColor: "#f5f7f2" },
  input: { flex: 1, minHeight: 44, maxHeight: 112, backgroundColor: "#fff", borderRadius: 8, borderWidth: 1, borderColor: "#d8dfd6", paddingHorizontal: 13, paddingVertical: 10, color: "#0f1f17", fontSize: 16 },
  sendButton: { width: 44, height: 44, borderRadius: 22, backgroundColor: "#007a5a", alignItems: "center", justifyContent: "center" },
  error: { color: "#b42318", marginVertical: 8 },
  heroCard: { backgroundColor: "#fff", borderRadius: 8, borderWidth: 1, borderColor: "#e1e6df", padding: 16, marginBottom: 16 },
  heroNumber: { color: "#0f1f17", fontSize: 52, lineHeight: 58, fontWeight: "800", marginTop: 6, letterSpacing: 0 },
  heroCopy: { color: "#566159", fontSize: 15, lineHeight: 22, marginTop: 12 },
  progressTrack: { height: 8, borderRadius: 999, backgroundColor: "#e6ebe4", overflow: "hidden", marginTop: 12 },
  progressFill: { height: "100%", borderRadius: 999 },
  goalCard: { backgroundColor: "#fff", borderRadius: 8, borderWidth: 1, borderColor: "#e1e6df", padding: 14, marginBottom: 10 },
  cardHeader: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: 10 },
  cardTitle: { color: "#0f1f17", fontSize: 16, lineHeight: 21, fontWeight: "800" },
  cardSubtitle: { color: "#68746b", fontSize: 13, lineHeight: 18, marginTop: 2 },
  cardValue: { color: "#0f1f17", fontSize: 16, fontWeight: "800" },
  cardFooter: { flexDirection: "row", justifyContent: "space-between", marginTop: 9 },
  formCard: { backgroundColor: "#fff", borderRadius: 8, borderWidth: 1, borderColor: "#e1e6df", overflow: "hidden", marginBottom: 16 },
  fieldRow: { minHeight: 56, flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 14, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: "#d8dfd6" },
  fieldLabel: { color: "#17231c", fontSize: 15 },
  fieldInput: { minWidth: 120, color: "#007a5a", fontSize: 15, textAlign: "right", paddingVertical: 10 },
  lastRow: { borderBottomWidth: 0 },
  allocationRow: { padding: 14, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: "#d8dfd6" },
  allocationTop: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: 10 },
  actionCard: { backgroundColor: "#fff", borderRadius: 8, borderWidth: 1, borderColor: "#e1e6df", padding: 14, marginBottom: 10, flexDirection: "row", alignItems: "center", gap: 12 },
  actionIcon: { width: 40, height: 40, borderRadius: 20, backgroundColor: "#e6f3ed", alignItems: "center", justifyContent: "center" },
  actionCopy: { flex: 1 },
  advisorHero: { backgroundColor: "#fff", borderRadius: 8, borderWidth: 1, borderColor: "#e1e6df", padding: 18, alignItems: "center", marginBottom: 16 },
  largeAvatar: { width: 84, height: 84, borderRadius: 42, backgroundColor: "#123d2d", alignItems: "center", justifyContent: "center", marginBottom: 12 },
  largeAvatarText: { color: "#fff", fontSize: 30, fontWeight: "800" },
  advisorName: { color: "#0f1f17", fontSize: 24, fontWeight: "800", letterSpacing: 0 },
  advisorTitle: { color: "#68746b", fontSize: 14, marginTop: 3 },
  advisorActions: { flexDirection: "row", gap: 10, marginTop: 18 },
  actionButton: { flex: 1, minHeight: 46, borderRadius: 8, backgroundColor: "#007a5a", flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 7, paddingHorizontal: 18 },
  actionButtonText: { color: "#fff", fontSize: 15, fontWeight: "800" },
  secondaryButton: { backgroundColor: "#e6f3ed" },
  secondaryButtonText: { color: "#007a5a" },
  tabBar: { flexDirection: "row", borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: "#d8dfd6", backgroundColor: "#fff", paddingTop: 8, paddingBottom: 8 },
  tabButton: { flex: 1, alignItems: "center", justifyContent: "center", minHeight: 48 },
  tabLabel: { color: "#7b827c", fontSize: 11, fontWeight: "700", marginTop: 3 },
  tabLabelActive: { color: "#007a5a" }
});
