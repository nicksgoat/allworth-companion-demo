import * as Linking from "expo-linking";
import React, { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { ApiClient } from "./api";
import type { ChatMessage, Dashboard } from "./types";

export type Mode = "client" | "advisor" | "vision";
export type ClientTab = "home" | "chat" | "profile";

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

export function AppProvider({ children }: { children: React.ReactNode }) {
  const api = useRef(new ApiClient()).current;
  const clientId = "maya";

  const [session, setSessionRaw] = useState("wednesday");
  const [mode, setMode] = useState<Mode>("client");
  const [selectedTab, setSelectedTab] = useState<ClientTab>("home");
  const [showDemoControls, setShowDemoControls] = useState(false);
  const [chatPrefill, setChatPrefill] = useState<string | null>(null);
  const [backendHost, setBackendHostRaw] = useState("localhost");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [dashboardError, setDashboardError] = useState<string | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [demoScreen, setDemoScreen] = useState<string | null>(null);

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
      } catch {
        setDashboardError(`Can't reach the backend at http://${backendHost}:3000 — run ./run.sh first.`);
      }
    };
    const resetDemo = async () => {
      try {
        await api.resetDemo(clientId);
      } catch {}
      setChatMessages([]);
      await loadDashboard();
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
      chatMessages,
      setChatMessages,
      resetDemo,
      demoScreen,
      clearDemoScreen: () => setDemoScreen(null),
    };
  }, [api, session, mode, selectedTab, showDemoControls, chatPrefill, backendHost, dashboard, dashboardError, chatMessages, demoScreen]);

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}
