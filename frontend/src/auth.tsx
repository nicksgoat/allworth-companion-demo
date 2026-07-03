import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { Platform } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";

import { getDefaultBaseURL } from "./api";

function getDefaultHost(): string {
  if (Platform.OS === "android") return "10.0.2.2";
  return "localhost";
}

const DEFAULT_HOST = getDefaultHost();

export interface AuthSession {
  token: string;
  householdId: string;
  email: string;
  contactName: string | null;
}

interface AuthState {
  session: AuthSession | null;
  loading: boolean;
  // True when the session came back from storage (app relaunch) rather than a
  // fresh email login — that's the case the biometric lock screen gates.
  restoredFromStorage: boolean;
  loginWithEmail: (email: string) => Promise<void>;
  logout: () => Promise<void>;
  /** Override backend host (for dev/demo) */
  backendHost: string;
  setBackendHost: (h: string) => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}

const STORAGE_KEY = "allworth_auth_session";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [restoredFromStorage, setRestoredFromStorage] = useState(false);
  const [backendHost, setBackendHostRaw] = useState(DEFAULT_HOST);

  // Restore saved session on mount — validate token is still good
  useEffect(() => {
    (async () => {
      try {
        const stored = await AsyncStorage.getItem(STORAGE_KEY);
        if (stored) {
          const parsed: AuthSession = JSON.parse(stored);
          // Validate the token against the backend
          const url =
            backendHost === DEFAULT_HOST ? getDefaultBaseURL() : `http://${backendHost}:3000`;
          const res = await fetch(`${url}/api/auth/me`, {
            headers: { Authorization: `Bearer ${parsed.token}` },
          });
          if (res.ok) {
            setRestoredFromStorage(true);
            setSession(parsed);
          } else {
            // Token expired or backend restarted — clear stale session
            await AsyncStorage.removeItem(STORAGE_KEY);
          }
        }
      } catch {
        // Network error — still try to use the stored session
        try {
          const stored = await AsyncStorage.getItem(STORAGE_KEY);
          if (stored) {
            setRestoredFromStorage(true);
            setSession(JSON.parse(stored));
          }
        } catch {}
      }
      setLoading(false);
    })();
  }, []);

  const baseURL = backendHost === DEFAULT_HOST ? getDefaultBaseURL() : `http://${backendHost}:3000`;

  const value = useMemo<AuthState>(() => {
    const loginWithEmail = async (email: string) => {
      const res = await fetch(`${baseURL}/api/auth/login/email`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `Login failed (${res.status})`);
      }
      const data = await res.json();
      const newSession: AuthSession = {
        token: data.token,
        householdId: data.householdId,
        email: data.email,
        contactName: data.contactName ?? null,
      };
      setRestoredFromStorage(false);
      setSession(newSession);
      await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(newSession));
    };

    const logout = async () => {
      if (session?.token) {
        try {
          await fetch(`${baseURL}/api/auth/logout`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${session.token}`,
            },
          });
        } catch {}
      }
      setSession(null);
      await AsyncStorage.removeItem(STORAGE_KEY);
    };

    const setBackendHost = (h: string) => {
      setBackendHostRaw(h);
    };

    return {
      session,
      loading,
      restoredFromStorage,
      loginWithEmail,
      logout,
      backendHost,
      setBackendHost,
    };
  }, [session, loading, restoredFromStorage, backendHost, baseURL]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
