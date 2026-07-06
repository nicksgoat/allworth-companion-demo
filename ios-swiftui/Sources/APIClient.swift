import Foundation

// Thin async client for the same backend the RN app uses (src/api.ts). Live data
// for the tabs, goal planning, and advisor interjection all go through here.
// Defaults to the local dev backend; override with BACKEND_URL.
enum APIClient {
    static var baseURL: String {
        ProcessInfo.processInfo.environment["BACKEND_URL"] ?? "http://localhost:3000"
    }
    static let clientId = "maya"
    static let advisorId = "nicole"

    struct APIError: Error { let message: String }

    static func get<T: Decodable>(_ path: String) async throws -> T {
        guard let url = URL(string: baseURL + path) else { throw APIError(message: "bad url") }
        let (data, resp) = try await URLSession.shared.data(from: url)
        try check(resp, data)
        return try JSONDecoder().decode(T.self, from: data)
    }

    @discardableResult
    static func post<T: Decodable>(_ path: String, body: [String: Any]) async throws -> T {
        guard let url = URL(string: baseURL + path) else { throw APIError(message: "bad url") }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, resp) = try await URLSession.shared.data(for: req)
        try check(resp, data)
        return try JSONDecoder().decode(T.self, from: data)
    }

    private static func check(_ resp: URLResponse, _ data: Data) throws {
        guard let http = resp as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw APIError(message: "HTTP \((resp as? HTTPURLResponse)?.statusCode ?? -1)")
        }
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
