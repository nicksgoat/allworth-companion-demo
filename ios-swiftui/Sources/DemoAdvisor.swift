import SwiftUI

// App-wide mode (client tabs vs. the advisor's book). The RN app calls
// app.setMode("advisor"/"client"); here it's one observable flag.
@Observable final class AppModel {
    var advisorMode = false
}

// Advisor-mode data, ported from backend/tests/goldens/{book,brief}.json.
extension Demo {
    struct Household: Identifiable, Hashable {
        let id: String            // clientId
        let name: String
        let managed: Int
        let heldAway: Int
        let openNudges: Int
        let highlight: Bool
    }

    static let book: [Household] = [
        .init(id: "maya", name: "Maya Tran", managed: 2_445_000, heldAway: 611_000, openNudges: 3, highlight: true),
        .init(id: "hh_castillo", name: "Robert & Elaine Castillo", managed: 3_120_000, heldAway: 188_000, openNudges: 0, highlight: false),
        .init(id: "hh_raman", name: "Priya Raman", managed: 1_870_000, heldAway: 0, openNudges: 1, highlight: false),
        .init(id: "hh_beckett", name: "Tom Beckett", managed: 2_410_000, heldAway: 452_000, openNudges: 0, highlight: false),
        .init(id: "hh_lindqvist", name: "Susan & Gary Lindqvist", managed: 5_230_000, heldAway: 74_000, openNudges: 0, highlight: false),
    ]

    struct HeldAccount: Identifiable, Hashable {
        let id: String
        let name: String
        let institution: String
        let balance: Int
    }

    // Maya's auto-prepared brief (brief.json)
    static let briefNarrative: [String] = [
        "Maya is weighing a $200,000 allocation to the SpaceX IPO with a 2026-06-15 deadline — she has worked through funding sources with the assistant and has open questions on liquidity vs. her $9,000/mo income draw.",
        "Held-away assets detected: $611,000 across 4 outside accounts (largest: Fidelity 401(k), $385,000) — a consolidation conversation may be timely if the IPO discussion opens the door.",
        "Open nudge: spending is running above plan (18% over plan).",
        "She prefers plain-English explanations and is tax-sensitive about her 2015 Apple shares.",
    ]
    static let briefOutsideAccounts: [HeldAccount] = [
        .init(id: "acct_401k", name: "401(k) — Former Employer", institution: "Fidelity", balance: 385_000),
        .init(id: "acct_rh", name: "Brokerage", institution: "Robinhood", balance: 96_000),
        .init(id: "acct_chk", name: "Checking", institution: "Chase", balance: 28_000),
        .init(id: "acct_sav", name: "Savings", institution: "Chase", balance: 102_000),
        .init(id: "acct_mtg", name: "Mortgage", institution: "Chase", balance: -310_000),
    ]

    struct ConvRef: Hashable { let clientId: String; let clientName: String }
    struct ConvMsg: Identifiable {
        let id = UUID()
        let role: Role
        let text: String
        var advisorName: String? = nil
        enum Role { case user, assistant, advisor }
    }
    // A representative thread for Maya (from the Monday session golden) showing
    // all three bubble types the RN transcript renders.
    static let conversation: [ConvMsg] = [
        .init(role: .user, text: "I want to put $200K into the SpaceX IPO. I have about 6 days to decide. What would that do to my taxes and my income plan? Explain it like I'm not a finance person, please."),
        .init(role: .assistant, text: "We walked through where $200K could come from — cash and money market (~$206K available, essentially no tax), selling the Apple position in your trust (~$170K, with an estimated $18,500 in capital-gains tax but it would also reduce your single-stock concentration), or selling Robinhood holdings (~$96K, an estimated $14,500 tax on very low-basis tech shares). We also looked at what a $200K illiquid position means for your $9,000/mo income plan while spending is running ~18% above plan. We ended with a list of questions to bring to Nicole before the June 15 deadline."),
        .init(role: .advisor, text: "Maya — let's not rush the SpaceX decision. I'll bring two funding paths that protect the income plan and keep the lake house on track. Thursday still good?", advisorName: "Nicole Mayer"),
    ]
}
