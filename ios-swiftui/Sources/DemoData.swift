import SwiftUI

// Static demo content mirroring the RN app's synthetic data (Maya Tran / Nicole
// Mayer). No backend — this is a UI copy, so everything is hard-coded here.

struct Nudge: Identifiable {
    let id = UUID()
    let icon: String        // SF Symbol
    let tone: Tone
    let title: String
    let sub: String
    enum Tone { case attention, info }
}

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

    static let nudges: [Nudge] = [
        Nudge(icon: "chart.line.uptrend.xyaxis", tone: .attention,
              title: "Spending is running above plan", sub: "18% over plan"),
        Nudge(icon: "chart.pie", tone: .info,
              title: "NVDA is a large share of your Robinhood account", sub: "54% of the account"),
        Nudge(icon: "chart.pie", tone: .info,
              title: "TSLA is a large share of your Robinhood account", sub: "26% of the account"),
        Nudge(icon: "wallet.bifold", tone: .info,
              title: "Money held outside your plan", sub: "$611,000 held away — worth a conversation"),
    ]

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
        let label: String
        let color: Color
        let value: Int
        let pct: Int
    }
    static let allocation: [AllocClass] = [
        .init(label: "US stocks", color: .chartNightBlue, value: 1_663_363, pct: 57),
        .init(label: "International stocks", color: .chartSky, value: 256_065, pct: 9),
        .init(label: "Bonds", color: .chartGold, value: 569_821, pct: 19),
        .init(label: "Municipal bonds", color: .chartEvergreen, value: 331_264, pct: 11),
        .init(label: "Cash", color: .chartLightGray, value: 104_826, pct: 4),
    ]
    static let equityPct = 66
    static let driftText =
        "About 6 points overweight stocks vs your 60/40 growth & income plan."

    // Wealth — concentration insights
    struct Concentration: Identifiable {
        let id = UUID()
        let pct: Int
        let title: String
    }
    static let concentration: [Concentration] = [
        .init(pct: 54, title: "NVDA is a large share of your Robinhood account"),
        .init(pct: 26, title: "TSLA is a large share of your Robinhood account"),
    ]

    static let recurringMonthly = "$3,667/mo"
    static let recurringNext = "Next deposit Aug 1"

    static func greetingForNow() -> String {
        let h = Calendar.current.component(.hour, from: Date())
        if h < 12 { return "Good morning" }
        if h < 17 { return "Good afternoon" }
        return "Good evening"
    }
}
