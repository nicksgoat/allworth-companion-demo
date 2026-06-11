import { fetch as expoFetch } from "expo/fetch";
import { Platform } from "react-native";
import type {
  AdvisorBrief,
  BookResponse,
  ChatEvent,
  Dashboard,
  ProactiveResponse,
  ProfileResponse,
  SpendingDetail,
} from "./types";

// Android emulators reach the host machine at 10.0.2.2, not localhost.
export const DEFAULT_HOST = Platform.OS === "android" ? "10.0.2.2" : "localhost";

export class ApiClient {
  baseURL = `http://${DEFAULT_HOST}:3000`;

  private async get<T>(path: string): Promise<T> {
    const res = await fetch(this.baseURL + path);
    if (!res.ok) throw new Error(`GET ${path} → ${res.status}`);
    return res.json();
  }

  dashboard(clientId: string): Promise<Dashboard> {
    return this.get(`/api/clients/${clientId}/dashboard`);
  }

  spending(clientId: string): Promise<SpendingDetail> {
    return this.get(`/api/clients/${clientId}/spending`);
  }

  profile(clientId: string): Promise<ProfileResponse> {
    return this.get(`/api/clients/${clientId}/profile`);
  }

  proactive(clientId: string, session: string): Promise<ProactiveResponse> {
    return this.get(`/api/clients/${clientId}/proactive?session=${session}`);
  }

  book(advisorId: string): Promise<BookResponse> {
    return this.get(`/api/advisors/${advisorId}/book`);
  }

  brief(advisorId: string, clientId: string): Promise<AdvisorBrief> {
    return this.get(`/api/advisors/${advisorId}/clients/${clientId}/brief`);
  }

  async forgetFact(clientId: string, factId: string): Promise<void> {
    const res = await fetch(`${this.baseURL}/api/clients/${clientId}/facts/${factId}`, { method: "DELETE" });
    if (!res.ok) throw new Error(`DELETE fact → ${res.status}`);
  }

  async resetDemo(clientId: string): Promise<void> {
    await fetch(this.baseURL + "/api/demo/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clientId }),
    });
  }

  // SSE chat — expo/fetch supports response body streaming (RN fetch does not)
  async *chat(clientId: string, session: string, message: string): AsyncGenerator<ChatEvent> {
    let res;
    try {
      res = await expoFetch(this.baseURL + "/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clientId, session, message }),
      });
    } catch {
      yield { kind: "error", message: "Couldn't reach the assistant. Is the backend running?" };
      return;
    }
    if (!res.body) {
      yield { kind: "error", message: "Couldn't reach the assistant. Is the backend running?" };
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let eventName = "";

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let nl: number;
        while ((nl = buffer.indexOf("\n")) >= 0) {
          const line = buffer.slice(0, nl).replace(/\r$/, "");
          buffer = buffer.slice(nl + 1);

          if (line.startsWith("event: ")) {
            eventName = line.slice(7);
          } else if (line.startsWith("data: ")) {
            const event = parseEvent(eventName, line.slice(6));
            if (event) yield event;
          }
        }
      }
    } catch {
      yield { kind: "error", message: "Connection lost. Please try again." };
    }
  }
}

function parseEvent(event: string, json: string): ChatEvent | null {
  let obj: any;
  try {
    obj = JSON.parse(json);
  } catch {
    return null;
  }
  switch (event) {
    case "tool_start":
      return { kind: "tool_start", name: obj.name ?? "", label: obj.label ?? "Working…" };
    case "tool_end":
      return { kind: "tool_end", name: obj.name ?? "" };
    case "text":
      return { kind: "text", delta: obj.delta ?? "" };
    case "done":
      return { kind: "done", sources: obj.sources ?? [], fallback: obj.fallback ?? false, suggested: obj.suggested ?? [] };
    case "error":
      return { kind: "error", message: obj.message ?? "Something went wrong." };
    default:
      return null;
  }
}
