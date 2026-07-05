import SwiftUI

// Static demo content mirroring the RN app's synthetic data (Maya Tran / Nicole
// Mayer). No backend — this is a UI copy, so everything is hard-coded here.

struct QuickAction: Identifiable {
    let id = UUID()
    let icon: String
    let label: String
}

enum Demo {
    static let clientFirstName = "Maya"
    static let clientName = "Maya Tran"
    static let clientMeta = "Plano, TX · Age 58"

    static let advisorName = "Nicole Mayer"
    static let advisorTitle = "Senior Financial Advisor, CFP®"
    static let advisorInitials = "NM"
    static let advisorLine = "Nicole Mayer · your advisor"
    static let advisorFirst = "Nicole"
    static let userEmail = "nicole@demo.com"

    // Profile
    static let clientCityAge = "Plano, TX  ·  Age 58"
    static let factsCount = 15
    static let learnedPreview =
        "Everything here came from you — each fact carries a source and an audit trail. Tap to review or remove."
    static let notesCount = 3
    static let latestNote = "Spring review & lake house planning"

    static let quickActions: [QuickAction] = [
        QuickAction(icon: "bubble.left", label: "Ask about spending"),
        QuickAction(icon: "flag", label: "My goals"),
        QuickAction(icon: "calendar", label: "Book Nicole"),
        QuickAction(icon: "folder", label: "Documents"),
    ]

    // Wealth — breakdown
    static let accountCount = 8
    static let managed = 2_445_000
    static let heldAway = 611_000
    static let liabilities = 310_000

    // Wealth — allocation (matches the RN donut + legend exactly)
    struct AllocClass: Identifiable {
        let id = UUID()
        let key: String
        let label: String
        let color: Color
        let value: Int
        let pct: Int
    }
    static let allocation: [AllocClass] = [
        .init(key: "us_equity", label: "US stocks", color: .chartNightBlue, value: 1_663_363, pct: 57),
        .init(key: "intl_equity", label: "International stocks", color: .chartSky, value: 256_065, pct: 9),
        .init(key: "bond", label: "Bonds", color: .chartGold, value: 569_821, pct: 19),
        .init(key: "muni_bond", label: "Municipal bonds", color: .chartEvergreen, value: 331_264, pct: 11),
        .init(key: "cash", label: "Cash", color: .chartLightGray, value: 104_826, pct: 4),
    ]
    static let equityPct = 66
    static let driftText =
        "About 6 points overweight stocks vs your 60/40 growth & income plan."

    static let recurringMonthly = "$3,667/mo"
    static let recurringNext = "Next deposit Aug 1"

    static func greetingForNow() -> String {
        let h = Calendar.current.component(.hour, from: Date())
        if h < 12 { return "Good morning" }
        if h < 17 { return "Good afternoon" }
        return "Good evening"
    }
}
