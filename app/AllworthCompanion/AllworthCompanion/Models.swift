import Foundation

struct ClientPersona: Codable, Identifiable {
    let id: String
    let name: String
    let age: Int
    let city: String
    let advisorId: String
    let bio: String
    let avatarInitials: String
}

struct Advisor: Codable, Identifiable {
    let id: String
    let name: String
    let title: String
    let avatarInitials: String
}

struct Account: Codable, Identifiable {
    let id: String
    let name: String
    let institution: String
    let group: String
    let type: String
    let balance: Int
    let history: [Int]?
}

struct MonthValue: Codable, Identifiable {
    let month: String
    let value: Int
    var id: String { month }
}

struct Nudge: Codable, Identifiable {
    let id: String
    let type: String
    let title: String
    let headline: String
    let body: String
    let cta: String
    let advisorCta: String
    let severity: String
}

struct LiquidityEvent: Codable {
    let label: String
    let amount: Int
    let deadline: String
    let note: String
}

struct SpendingSnapshot: Codable {
    let avg3mo: Int
    let plan: Int
    let overPlanPct: Int
}

struct Dashboard: Codable {
    let client: ClientPersona?
    let advisor: Advisor
    let netWorth: Int
    let netWorthHistory: [MonthValue]
    let allworthTotal: Int
    let heldAwayTotal: Int
    let liabilitiesTotal: Int
    let accounts: AccountGroups
    let spending: SpendingSnapshot
    let nudges: [Nudge]
    let liquidityEvent: LiquidityEvent
    let disclaimer: String

    struct AccountGroups: Codable {
        let allworth: [Account]
        let outside: [Account]
    }
}

struct SpendingMonth: Codable, Identifiable {
    let month: String
    let total: Int
    let planned: Int
    let categories: [String: Int]
    var id: String { month }
}

struct SpendingDetail: Codable {
    let months: [SpendingMonth]
    let all: [SpendingMonth]
    let avg3mo: Int
    let plan: Int
    let overPlanPct: Int
}

struct LearnedFact: Codable, Identifiable {
    let fact: String
    let category: String
    let sourceQuote: String
    let learnedAt: String
    let confidence: Double
    let status: String

    var id: String { fact }

    enum CodingKeys: String, CodingKey {
        case fact, category, confidence, status
        case sourceQuote = "source_quote"
        case learnedAt = "learned_at"
    }
}

struct ProfileResponse: Codable {
    let clientId: String
    let facts: [LearnedFact]
}

struct ProactiveResponse: Codable {
    let message: String
}

struct BookResponse: Codable {
    let advisor: Advisor
    let households: [Household]
}

struct Household: Codable, Identifiable {
    let clientId: String
    let name: String
    let managedAssets: Int
    let heldAwayDetected: Int
    let openNudges: Int
    let lastContact: String
    let highlight: Bool?
    var id: String { clientId }
}

struct AdvisorBrief: Codable {
    let client: ClientPersona?
    let managedTotal: Int
    let heldAwayDetected: Int
    let heldAwayAccounts: [Account]
    let liabilities: [Account]
    let openNudges: [Nudge]
    let profile: [LearnedFact]
    let liquidityEvent: LiquidityEvent
    let narrative: String
}

// MARK: - Chat

enum ChatRole { case user, assistant }

struct ToolChip: Identifiable, Equatable {
    let name: String
    let label: String
    var running: Bool
    var id: String { name }
}

struct ChatMessage: Identifiable {
    let id = UUID()
    let role: ChatRole
    var text: String
    var chips: [ToolChip] = []
    var sources: [String] = []
    var isStreaming = false
}

enum ChatEvent {
    case toolStart(name: String, label: String)
    case toolEnd(name: String)
    case text(delta: String)
    case done(sources: [String], fallback: Bool)
    case error(message: String)
}
