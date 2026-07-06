import Foundation

// Thin async client for the same backend the RN app uses (src/api.ts). Live data
// for the tabs, goal planning, and advisor interjection all go through here.
// Defaults to the local dev backend; override with BACKEND_URL.
enum APIClient {
    // Demoable anywhere: defaults to the deployed HTTPS backend. Override with
    // BACKEND_URL (e.g. http://localhost:3000) for local development.
    static var baseURL: String {
        ProcessInfo.processInfo.environment["BACKEND_URL"] ?? "https://allworth-demo-api.fly.dev"
    }
    static let clientId = "maya"
    static let advisorId = "nicole"
    static var token: String?          // set after login; sent as Bearer

    struct APIError: Error { let message: String }

    private static func request(_ path: String, method: String, body: Data? = nil) throws -> URLRequest {
        guard let url = URL(string: baseURL + path) else { throw APIError(message: "bad url") }
        var req = URLRequest(url: url)
        req.httpMethod = method
        if let body { req.httpBody = body; req.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        if let token { req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        return req
    }

    static func get<T: Decodable>(_ path: String) async throws -> T {
        let (data, resp) = try await URLSession.shared.data(for: request(path, method: "GET"))
        try check(resp, data)
        return try JSONDecoder().decode(T.self, from: data)
    }

    @discardableResult
    static func post<T: Decodable>(_ path: String, body: [String: Any]) async throws -> T {
        let data = try JSONSerialization.data(withJSONObject: body)
        let (out, resp) = try await URLSession.shared.data(for: request(path, method: "POST", body: data))
        try check(resp, out)
        return try JSONDecoder().decode(T.self, from: out)
    }

    private static func check(_ resp: URLResponse, _ data: Data) throws {
        guard let http = resp as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw APIError(message: "HTTP \((resp as? HTTPURLResponse)?.statusCode ?? -1)")
        }
    }

    // MARK: Auth
    struct LoginResponse: Decodable { let token: String; let householdId: String?; let contactName: String? }
    static func login(email: String) async throws -> LoginResponse {
        try await post("/api/auth/login/email", body: ["email": email])
    }

    // MARK: Goals
    static func goals() async throws -> GoalsResponse {
        try await get("/api/clients/\(clientId)/goals")
    }
    struct SavePlanResponse: Decodable { let goalId: String }
    @discardableResult
    static func saveGoalPlan(goalId: String, monthly: Double, years: Int) async throws -> SavePlanResponse {
        try await post("/api/clients/\(clientId)/goals/\(goalId)/plan", body: ["monthly": monthly, "years": years])
    }

    // MARK: Conversation + advisor interjection (three-way chat)
    static func conversation(session: String) async throws -> ConversationResponse {
        try await get("/api/clients/\(clientId)/conversation?session=\(session)")
    }
    struct InterjectResponse: Decodable { let message: ConvMessage }
    @discardableResult
    static func interject(session: String, text: String) async throws -> InterjectResponse {
        try await post("/api/advisors/clients/\(clientId)/interject", body: ["session": session, "text": text])
    }
}

struct ConversationResponse: Decodable { let messages: [ConvMessage] }
struct ConvMessage: Decodable {
    let id: String?
    let seq: Int?
    let role: String            // "user" | "assistant" | "advisor"
    let text: String
    let advisorName: String?
    var key: String { id ?? "seq-\(seq ?? -1)" }
}

struct GoalsResponse: Decodable {
    let goals: [APIGoal]
    let summary: String
    let assumedGrowthRate: Double?
}

struct APIGoal: Decodable, Identifiable {
    let id: String
    let label: String
    let type: String            // "lump_sum" | "income"
    let target: Int?
    let currentFunded: Int?
    let fundedPct: Int?
    let horizonYears: Int?
    let onTrack: Bool?
    let monthlyContributionToClose: Int?
    let committedMonthly: Double?
    let committedYears: Int?
    let projectedWithPlan: Int?
    let onTrackWithPlan: Bool?
    let detail: String?         // income goals
    let status: String?

    var isIncome: Bool { type == "income" }
}

// Future value with monthly compounding — matches the backend's projection so the
// dial reprojects live without a round-trip on every drag.
func projectGoal(current: Double, monthly: Double, years: Int, annualRate: Double) -> Double {
    let n = Double(years) * 12
    let r = annualRate / 12
    guard r > 0 else { return current + monthly * n }
    let growth = pow(1 + r, n)
    return current * growth + monthly * ((growth - 1) / r)
}
