import Foundation

// Streams the LIVE assistant from the backend's SSE endpoint (POST /api/chat),
// the same one the RN app uses. Events mirror api.ts: tool_start / tool_end /
// text (token deltas) / done (sources + suggested chips) / error.
enum ChatStreamEvent {
    case toolStart(label: String)
    case toolEnd(ToolWidget?)          // carries the structured result for visual tools
    case text(String)
    case done(sources: [String], suggested: [String])
    case error(String)
}

enum ChatService {
    // Defaults to the deployed HTTPS backend; override with BACKEND_URL for local dev.
    static var baseURL: String {
        ProcessInfo.processInfo.environment["BACKEND_URL"] ?? "https://allworth-demo-api.fly.dev"
    }

    static func stream(clientId: String, session: String, message: String,
                       conversationId: String? = nil) -> AsyncStream<ChatStreamEvent> {
        AsyncStream { continuation in
            let task = Task {
                guard let url = URL(string: baseURL + "/api/chat") else {
                    continuation.yield(.error("Bad backend URL")); continuation.finish(); return
                }
                var req = URLRequest(url: url)
                req.httpMethod = "POST"
                req.setValue("application/json", forHTTPHeaderField: "Content-Type")
                req.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                if let t = APIClient.token { req.setValue("Bearer \(t)", forHTTPHeaderField: "Authorization") }
                req.timeoutInterval = 90
                var payload: [String: Any] = ["clientId": clientId, "session": session, "message": message]
                if let conversationId { payload["conversationId"] = conversationId }
                req.httpBody = try? JSONSerialization.data(withJSONObject: payload)

                do {
                    let (bytes, response) = try await URLSession.shared.bytes(for: req)
                    guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
                        continuation.yield(.error("Couldn't reach the assistant.")); continuation.finish(); return
                    }
                    var eventName = ""
                    for try await line in bytes.lines {
                        if Task.isCancelled { break }
                        if line.hasPrefix("event:") {
                            eventName = line.dropFirst(6).trimmingCharacters(in: .whitespaces)
                        } else if line.hasPrefix("data:") {
                            let json = String(line.dropFirst(5).drop(while: { $0 == " " }))
                            if let ev = parse(eventName, json) { continuation.yield(ev) }
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.yield(.error("Couldn't reach the assistant. Is the backend running?"))
                    continuation.finish()
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    private static func parse(_ event: String, _ json: String) -> ChatStreamEvent? {
        guard let data = json.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        switch event {
        case "tool_start": return .toolStart(label: obj["label"] as? String ?? "Working…")
        case "tool_end": return .toolEnd(ToolWidget.from(obj["result"] as? [String: Any]))
        case "text": return .text(obj["delta"] as? String ?? "")
        case "done": return .done(sources: strings(obj["sources"]), suggested: strings(obj["suggested"]))
        case "error": return .error(obj["message"] as? String ?? "Something went wrong.")
        default: return nil
        }
    }

    // Sources/suggested may arrive as plain strings or as objects — accept both.
    private static func strings(_ any: Any?) -> [String] {
        guard let arr = any as? [Any] else { return [] }
        return arr.compactMap { item in
            if let s = item as? String { return s }
            if let d = item as? [String: Any] {
                return (d["title"] ?? d["label"] ?? d["name"] ?? d["text"]) as? String
            }
            return nil
        }
    }
}
