import Foundation

actor APIClient {
    var baseURL: URL

    init(baseURL: URL = URL(string: "http://localhost:3000")!) {
        self.baseURL = baseURL
    }

    func setBaseURL(_ url: URL) { baseURL = url }

    private func get<T: Decodable>(_ path: String) async throws -> T {
        // URL(string:relativeTo:) keeps query strings intact; appending(path:) would escape "?"
        guard let url = URL(string: path, relativeTo: baseURL) else { throw URLError(.badURL) }
        let (data, _) = try await URLSession.shared.data(from: url)
        return try JSONDecoder().decode(T.self, from: data)
    }

    func dashboard(clientId: String) async throws -> Dashboard {
        try await get("/api/clients/\(clientId)/dashboard")
    }

    func spending(clientId: String) async throws -> SpendingDetail {
        try await get("/api/clients/\(clientId)/spending")
    }

    func profile(clientId: String) async throws -> ProfileResponse {
        try await get("/api/clients/\(clientId)/profile")
    }

    func proactive(clientId: String, session: String) async throws -> ProactiveResponse {
        try await get("/api/clients/\(clientId)/proactive?session=\(session)")
    }

    func book(advisorId: String) async throws -> BookResponse {
        try await get("/api/advisors/\(advisorId)/book")
    }

    func brief(advisorId: String, clientId: String) async throws -> AdvisorBrief {
        try await get("/api/advisors/\(advisorId)/clients/\(clientId)/brief")
    }

    func resetDemo(clientId: String) async throws {
        var req = URLRequest(url: baseURL.appending(path: "/api/demo/reset"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode(["clientId": clientId])
        _ = try await URLSession.shared.data(for: req)
    }

    // MARK: - SSE chat

    func chat(clientId: String, session: String, message: String) -> AsyncStream<ChatEvent> {
        let url = baseURL.appending(path: "/api/chat")
        return AsyncStream { continuation in
            let task = Task {
                do {
                    var req = URLRequest(url: url)
                    req.httpMethod = "POST"
                    req.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    req.timeoutInterval = 120
                    req.httpBody = try JSONEncoder().encode(
                        ["clientId": clientId, "session": session, "message": message])

                    let (bytes, _) = try await URLSession.shared.bytes(for: req)
                    var eventName = ""
                    for try await line in bytes.lines {
                        if line.hasPrefix("event: ") {
                            eventName = String(line.dropFirst(7))
                        } else if line.hasPrefix("data: ") {
                            let json = Data(line.dropFirst(6).utf8)
                            if let event = Self.parse(eventName, json) {
                                continuation.yield(event)
                            }
                        }
                    }
                } catch {
                    continuation.yield(.error(message: "Couldn't reach the assistant. Is the backend running?"))
                }
                continuation.finish()
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    private static func parse(_ event: String, _ data: Data) -> ChatEvent? {
        guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        switch event {
        case "tool_start":
            return .toolStart(name: obj["name"] as? String ?? "", label: obj["label"] as? String ?? "Working…")
        case "tool_end":
            return .toolEnd(name: obj["name"] as? String ?? "")
        case "text":
            return .text(delta: obj["delta"] as? String ?? "")
        case "done":
            return .done(sources: obj["sources"] as? [String] ?? [], fallback: obj["fallback"] as? Bool ?? false)
        case "error":
            return .error(message: obj["message"] as? String ?? "Something went wrong.")
        default:
            return nil
        }
    }
}
