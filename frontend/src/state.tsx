import * as Linking from "expo-linking";
import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { ApiClient, AuthError, DEFAULT_HOST, getDefaultBaseURL } from "./api";
import { useAuth } from "./auth";
import type { ChatMessage, Dashboard, Portfolio } from "./types";

export type Mode = "client" | "advisor" | "vision";
export type ClientTab = "home" | "invest" | "chat" | "profile";

interface AppState {
  api: ApiClient;
  clientId: string;
  session: string;
  setSession: (s: string) => void;
  mode: Mode;
  setMode: (m: Mode) => void;
  selectedTab: ClientTab;
  setSelectedTab: (t: ClientTab) => void;
  showDemoControls: boolean;
  setShowDemoControls: (v: boolean) => void;
  chatPrefill: string | null;
  setChatPrefill: (v: string | null) => void;
  backendHost: string;
  setBackendHost: (h: string) => void;
  dashboard: Dashboard | null;
  dashboardError: string | null;
  loadDashboard: () => Promise<void>;
  portfolio: Portfolio | null;
  portfolioError: string | null;
  loadPortfolio: () => Promise<void>;
  chatMessages: ChatMessage[];
  setChatMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  resetDemo: () => Promise<void>;
  demoScreen: string | null;
  clearDemoScreen: () => void;
}

const AppContext = createContext<AppState | null>(null);

export function useApp(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp outside AppProvider");
  return ctx;
}

// Module-level singleton: AppProvider mounts once, and demo controls mutate
// api.baseURL directly (not allowed on useRef/useState values by lint rules).
const api = new ApiClient();

export function AppProvider({ children }: { children: React.ReactNode }) {
  const { session: authSession, backendHost: authHost, logout } = useAuth();
  const clientId = authSession?.householdId ?? "maya";

  const [session, setSessionRaw] = useState("wednesday");
  const [mode, setMode] = useState<Mode>("client");
  const [selectedTab, setSelectedTab] = useState<ClientTab>("home");
  const [showDemoControls, setShowDemoControls] = useState(false);
  const [chatPrefill, setChatPrefill] = useState<string | null>(null);
  const [backendHost, setBackendHostRaw] = useState(DEFAULT_HOST);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [dashboardError, setDashboardError] = useState<string | null>(null);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [portfolioError, setPortfolioError] = useState<string | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [demoScreen, setDemoScreen] = useState<string | null>(null);

  // Sync auth token synchronously — must happen before children's effects
  // fire (e.g. DashboardScreen calling loadDashboard on mount).
  // Using useEffect would be too late because children's effects run first.
  api.token = authSession?.token ?? null;
  api.onAuthError = () => {
    logout();
  };

  useEffect(() => {
    api.baseURL = getDefaultBaseURL();
  }, [authHost]);

  // Deep-link demo overrides for automated verification (replaces the Swift
  // DEMO_SCREEN launch env): xcrun simctl openurl booted "allworthdemo://demo/<screen>"
  useEffect(() => {
    const apply = (url: string | null) => {
      const screen = url?.match(/demo\/([a-z_]+)/)?.[1];
      if (!screen) return;
      switch (screen) {
        case "chat":
          setMode("client");
          setSelectedTab("chat");
          break;
        case "invest":
          setMode("client");
          setSelectedTab("invest");
          break;
        case "profile":
          setMode("client");
          setSelectedTab("profile");
          break;
        case "fact":
          setMode("client");
          setSelectedTab("profile");
          setDemoScreen("fact");
          break;
        case "advisor":
          setMode("advisor");
          break;
        case "advisor_detail":
          setMode("advisor");
          setDemoScreen("advisor_detail");
          break;
        case "vision":
          setMode("vision");
          break;
        case "controls":
          setShowDemoControls(true);
          break;
        case "nudge":
          setMode("client");
          setSelectedTab("home");
          setDemoScreen("nudge");
          break;
      }
    };
    Linking.getInitialURL().then(apply);
    const sub = Linking.addEventListener("url", (e) => apply(e.url));
    return () => sub.remove();
  }, []);

  const value = useMemo<AppState>(() => {
    const setSession = (s: string) => {
      setSessionRaw(s);
      setChatMessages([]);
    };
    const setBackendHost = (h: string) => {
      setBackendHostRaw(h);
      api.baseURL = `http://${h}:3000`;
    };
    const loadDashboard = async () => {
      try {
        setDashboard(await api.dashboard(clientId));
        setDashboardError(null);
      } catch (e) {
        if (e instanceof AuthError) return; // onAuthError will trigger logout
        setDashboardError(
          `Can't reach the backend at ${api.baseURL} — run ./run.sh first.`,
        );
      }
    };
    const loadPortfolio = async () => {
      try {
        setPortfolio(await api.portfolio(clientId));
        setPortfolioError(null);
      } catch (e) {
        if (e instanceof AuthError) return; // onAuthError will trigger logout
        setPortfolioError(
          `Can't reach the backend at ${api.baseURL} — run ./run.sh first.`,
        );
      }
    };
    const resetDemo = async () => {
      try {
        await api.resetDemo(clientId);
      } catch {}
      setChatMessages([]);
      await Promise.all([loadDashboard(), loadPortfolio()]);
    };
    return {
      api,
      clientId,
      session,
      setSession,
      mode,
      setMode,
      selectedTab,
      setSelectedTab,
      showDemoControls,
      setShowDemoControls,
      chatPrefill,
      setChatPrefill,
      backendHost,
      setBackendHost,
      dashboard,
      dashboardError,
      loadDashboard,
      portfolio,
      portfolioError,
      loadPortfolio,
      chatMessages,
      setChatMessages,
      resetDemo,
      demoScreen,
      clearDemoScreen: () => setDemoScreen(null),
    };
  }, [
    session,
    mode,
    selectedTab,
    showDemoControls,
    chatPrefill,
    backendHost,
    dashboard,
    dashboardError,
    portfolio,
    portfolioError,
    chatMessages,
    demoScreen,
  ]);

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}
