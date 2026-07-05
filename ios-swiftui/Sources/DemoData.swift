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

    static let nudges: [Nudge] = [
        Nudge(icon: "chart.line.uptrend.xyaxis", tone: .attention,
              title: "Spending is running above plan", sub: "18% over plan"),
        Nudge(icon: "chart.pie", tone: .info,
              title: "NVDA is a large share of your Robinhood account", sub: "54% of the account"),
        Nudge(icon: "chart.pie", tone: .info,
              title: "TSLA is a large share of your Robinhood account", sub: "26% of the account"),
        Nudge(icon: "wallet.pass", tone: .info,
              title: "Money held outside your plan", sub: "$611,000 held away — worth a conversation"),
    ]

    static let quickActions: [QuickAction] = [
        QuickAction(icon: "bubble.left", label: "Ask about spending"),
        QuickAction(icon: "flag", label: "My goals"),
        QuickAction(icon: "calendar", label: "Book Nicole"),
        QuickAction(icon: "folder", label: "Documents"),
    ]

    static func greetingForNow() -> String {
        let h = Calendar.current.component(.hour, from: Date())
        if h < 12 { return "Good morning" }
        if h < 17 { return "Good afternoon" }
        return "Good evening"
    }
}
