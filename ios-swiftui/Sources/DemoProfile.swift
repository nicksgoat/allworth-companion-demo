import SwiftUI

// Profile data ported from the RN app: learned facts (memory/maya.runtime.json,
// the 15 active), meeting notes + goals (data/seed.json), and the hardcoded
// document vault (DocumentsSheet.tsx).

extension Demo {
    struct LearnedFact: Identifiable {
        let id: String
        let fact: String
        let quote: String
        let learned: String     // display date, e.g. "Jun 8, 2026"
        let confidence: Int     // percent
    }

    struct FactGroup: Identifiable {
        let id = UUID()
        let label: String       // humanized category label
        let facts: [LearnedFact]
    }

    // Grouped in the same first-seen category order the RN screen uses.
    static let factGroups: [FactGroup] = [
        FactGroup(label: "Decisions in motion", facts: [
            .init(id: "f0", fact: "Considering a $200K allocation to the SpaceX IPO, decision deadline around June 15",
                  quote: "I want to put $200K into the SpaceX IPO. I have about 6 days to decide.", learned: "Jun 8, 2026", confidence: 95),
        ]),
        FactGroup(label: "Your goals", facts: [
            .init(id: "f1", fact: "Planning to buy a lake house in about 4 years (~$350K goal)",
                  quote: "the lake house is still the big one for us", learned: "Jun 8, 2026", confidence: 92),
            .init(id: "f2", fact: "User wants to set aside money for their daughter's college tuition.",
                  quote: "My daughter Lily starts college next fall and I want to set aside money for her tuition.", learned: "Jun 21, 2026", confidence: 95),
            .init(id: "f3", fact: "Client wants to rebalance their portfolio to a 70/30 stock-bond mix.",
                  quote: "Rebalance my portfolio to a 70/30 stock-bond mix and show me the tax impact.", learned: "Jun 22, 2026", confidence: 95),
            .init(id: "f4", fact: "User is seeking to assess retirement comfortability using Monte Carlo projections.",
                  quote: "Run a Monte Carlo retirement projection — can I retire comfortably?", learned: "Jun 22, 2026", confidence: 90),
            .init(id: "f5", fact: "User is considering retirement and wants to evaluate their financial comfort.",
                  quote: "Run a Monte Carlo retirement projection — can I retire comfortably?", learned: "Jun 22, 2026", confidence: 90),
            .init(id: "f6", fact: "Client has a goal of obtaining a lake house.",
                  quote: "Am I on track for the lake house goal?", learned: "Jul 3, 2026", confidence: 90),
            .init(id: "f7", fact: "The client has a goal related to funding 529 plans for their grandchildren.",
                  quote: "Am I on track for the grandkids' 529s goal?", learned: "Jul 3, 2026", confidence: 90),
        ]),
        FactGroup(label: "Accounts you've mentioned", facts: [
            .init(id: "f8", fact: "Holds outside accounts: Fidelity 401(k) from former employer, Robinhood brokerage, Chase checking and savings",
                  quote: "between my old 401k and the Robinhood account", learned: "Jun 8, 2026", confidence: 97),
            .init(id: "f9", fact: "Client holds money outside Allworth.",
                  quote: "What should I be doing with the money I hold outside Allworth?", learned: "Jul 3, 2026", confidence: 90),
        ]),
        FactGroup(label: "Your preferences", facts: [
            .init(id: "f10", fact: "Reluctant to sell her oldest Apple shares because of the embedded capital gain",
                  quote: "I hate the idea of paying tax on the Apple I bought back in 2015", learned: "Jun 8, 2026", confidence: 88),
            .init(id: "f11", fact: "Semi-retired; earns about $4,500/mo from part-time consulting and prefers plain-English explanations over jargon",
                  quote: "explain it like I'm not a finance person, please", learned: "Jun 8, 2026", confidence: 90),
            .init(id: "f12", fact: "Client wants to understand the tax impact of portfolio rebalancing.",
                  quote: "show me the tax impact", learned: "Jun 22, 2026", confidence: 90),
        ]),
        FactGroup(label: "On your mind", facts: [
            .init(id: "f13", fact: "Aware her spending is running above plan and wants to understand what it means before changing anything",
                  quote: "I know we've been spending more the last few months", learned: "Jun 8, 2026", confidence: 85),
        ]),
        FactGroup(label: "Life events", facts: [
            .init(id: "f14", fact: "User's daughter Lily is starting college next fall.",
                  quote: "My daughter Lily starts college next fall and I want to set aside money for her tuition.", learned: "Jun 21, 2026", confidence: 90),
        ]),
    ]
    static var allFacts: [LearnedFact] { factGroups.flatMap { $0.facts } }

    struct MeetingNote: Identifiable {
        let id: String
        let title: String
        let date: String        // display, e.g. "May 21, 2026"
        let summary: String
        let advisor: String
        let attendees: [String]
    }
    static let meetingNotes: [MeetingNote] = [
        .init(id: "mn1", title: "Spring review & lake house planning", date: "May 21, 2026",
              summary: "Reviewed portfolio performance and the lake house goal (32% funded). Talked through pacing the $350K target over four years and funding it tax-aware from the trust account. Next: model two funding paths before the next session.",
              advisor: "Nicole Mayer", attendees: ["Maya Tran", "Nicole Mayer"]),
        .init(id: "mn2", title: "Spending check-in", date: "Apr 9, 2026",
              summary: "Spending is running about 18% over plan, mostly travel and gifts to family. Agreed it's sustainable near-term but worth revisiting if it carries into the lake house purchase window.",
              advisor: "Nicole Mayer", attendees: ["Maya Tran", "Nicole Mayer"]),
        .init(id: "mn3", title: "SpaceX IPO allocation", date: "Feb 18, 2026",
              summary: "Walked through the $200K SpaceX IPO opportunity — liquidity trade-offs against the $9K/mo income draw. Maya leaning cautious; revisit once the terms firm up.",
              advisor: "Nicole Mayer", attendees: ["Maya Tran", "Nicole Mayer"]),
    ]

    struct Document: Identifiable {
        let id = UUID()
        let icon: String        // SF Symbol
        let name: String
        let meta: String
    }
    static let documents: [Document] = [
        .init(icon: "doc.text", name: "Financial Plan — 2026 Review", meta: "Updated Jun 10, 2026 · PDF"),
        .init(icon: "receipt", name: "2025 Tax Return", meta: "Filed Apr 2026 · PDF"),
        .init(icon: "chart.bar", name: "Q2 2026 Consolidated Statement", meta: "Jun 30, 2026 · PDF"),
        .init(icon: "checkmark.shield", name: "Estate Plan Summary", meta: "Reviewed Jan 2026 · PDF"),
        .init(icon: "house", name: "Lake House Goal Worksheet", meta: "Shared by Nicole · May 2026"),
    ]

    struct Goal: Identifiable {
        let id: String
        let label: String
        let income: Bool
        let onTrack: Bool
        let currentFunded: Int
        let target: Int
        let fundedPct: Int
        let plan: String        // "your plan: $5,750/mo over 6 yrs" or income detail
    }
    static let goalsSummary = "3/3 goals on track"
    static let goals: [Goal] = [
        .init(id: "g1", label: "Lake house", income: false, onTrack: true, currentFunded: 112_000, target: 350_000, fundedPct: 32, plan: "your plan: $5,750/mo over 6 yrs"),
        .init(id: "g2", label: "Grandkids' 529s", income: false, onTrack: true, currentFunded: 21_600, target: 120_000, fundedPct: 18, plan: "your plan: $500/mo over 12 yrs"),
        .init(id: "g3", label: "Retirement income", income: true, onTrack: true, currentFunded: 0, target: 0, fundedPct: 0, plan: "$9,000/mo from portfolio through age 95"),
    ]

    // Concierge availability — mirrors the backend's "next 10 business days, a few
    // slots each" without a network call. Deterministic per day index.
    struct AvailDay: Identifiable {
        let id = UUID()
        let dow: String
        let dayNum: String
        let long: String
        let slots: [String]
    }
    static let availability: [AvailDay] = {
        let cal = Calendar(identifier: .gregorian)
        let dowShort = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        let dowLong = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        let pool = ["9:00 AM", "10:30 AM", "11:15 AM", "1:00 PM", "2:30 PM", "3:15 PM", "4:00 PM"]
        var out: [AvailDay] = []
        var day = Date()
        var idx = 0
        while out.count < 10 {
            day = cal.date(byAdding: .day, value: 1, to: day) ?? day
            let wd = cal.component(.weekday, from: day) - 1   // 0=Sun
            if wd == 0 || wd == 6 { continue }                // business days only
            let n = 3 + (idx % 2)                             // 3–4 slots
            let start = (idx * 2) % (pool.count - n)
            out.append(AvailDay(dow: dowShort[wd], dayNum: "\(cal.component(.day, from: day))",
                                long: dowLong[wd], slots: Array(pool[start..<start + n])))
            idx += 1
        }
        return out
    }()
}
