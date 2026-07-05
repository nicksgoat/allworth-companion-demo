import SwiftUI

// Portfolio data ported verbatim from backend/tests/goldens/{dashboard,portfolio,
// spending}.json — the same golden fixtures the RN app renders. Exact values so
// the Holdings tab and the detail sheets match 1:1.

extension Demo {
    struct Position: Identifiable {
        let id = UUID()
        let symbol: String
        let name: String
        let value: Int
        let assetClass: String   // us_equity | intl_equity | bond | muni_bond | cash
        let accountId: String
        var price: Double = 0
        var qty: Double = 0
        var costBasis: Int? = nil
        var averageCostBasis: Double? = nil
        var unrealizedGain: Int? = nil
        var longTermUnrealizedGain: Int? = nil
        var shortTermUnrealizedGain: Int? = nil
    }

    struct Account: Identifiable {
        let id: String
        let name: String
        let institution: String
        let balance: Int
        let positions: [Position]
    }

    // Account labels for holdings sublines: "<name> · <institution>"
    static func accountLabel(_ id: String) -> String {
        guard let a = accountsInvested.first(where: { $0.id == id }) else { return "" }
        return "\(a.name) · \(a.institution)"
    }

    static let accountsInvested: [Account] = [
        Account(id: "acct_trust", name: "Trust Brokerage", institution: "Allworth (Schwab)", balance: 1_420_000, positions: [
            Position(symbol: "VTI", name: "Vanguard Total Stock Market ETF", value: 483_800, assetClass: "us_equity", accountId: "acct_trust", price: 295, qty: 1640, costBasis: 371_185, averageCostBasis: 226.33, unrealizedGain: 112_615, longTermUnrealizedGain: 111_115, shortTermUnrealizedGain: 1_500),
            Position(symbol: "VTEB", name: "Vanguard Tax-Exempt Bond ETF", value: 331_264, assetClass: "muni_bond", accountId: "acct_trust", price: 51.2, qty: 6470, costBasis: 322_530, averageCostBasis: 49.85, unrealizedGain: 8_734, longTermUnrealizedGain: 8_734, shortTermUnrealizedGain: 0),
            Position(symbol: "AAPL", name: "Apple Inc.", value: 170_400, assetClass: "us_equity", accountId: "acct_trust", price: 213, qty: 800, costBasis: 79_160, averageCostBasis: 98.95, unrealizedGain: 91_240, longTermUnrealizedGain: 92_940, shortTermUnrealizedGain: -1_700),
            Position(symbol: "BND", name: "Vanguard Total Bond Market ETF", value: 167_352, assetClass: "bond", accountId: "acct_trust", price: 73.4, qty: 2280, costBasis: 170_886, averageCostBasis: 74.95, unrealizedGain: -3_534, longTermUnrealizedGain: -3_534, shortTermUnrealizedGain: 0),
            Position(symbol: "VXUS", name: "Vanguard Total Intl Stock ETF", value: 162_540, assetClass: "intl_equity", accountId: "acct_trust", price: 64.5, qty: 2520, costBasis: 138_852, averageCostBasis: 55.1, unrealizedGain: 23_688, longTermUnrealizedGain: 23_688, shortTermUnrealizedGain: 0),
            Position(symbol: "CASH", name: "Money Market Sweep", value: 104_644, assetClass: "cash", accountId: "acct_trust", price: 104_644, qty: 1),
        ]),
        Account(id: "acct_ira", name: "Rollover IRA", institution: "Allworth (Schwab)", balance: 880_000, positions: [
            Position(symbol: "VTI", name: "Vanguard Total Stock Market ETF", value: 439_550, assetClass: "us_equity", accountId: "acct_ira", price: 295, qty: 1490),
            Position(symbol: "BND", name: "Vanguard Total Bond Market ETF", value: 346_448, assetClass: "bond", accountId: "acct_ira", price: 73.4, qty: 4720),
            Position(symbol: "VXUS", name: "Vanguard Total Intl Stock ETF", value: 93_525, assetClass: "intl_equity", accountId: "acct_ira", price: 64.5, qty: 1450),
        ]),
        Account(id: "acct_roth", name: "Roth IRA", institution: "Allworth (Schwab)", balance: 145_000, positions: [
            Position(symbol: "VTI", name: "Vanguard Total Stock Market ETF", value: 144_845, assetClass: "us_equity", accountId: "acct_roth", price: 295, qty: 491),
        ]),
        Account(id: "acct_401k", name: "401(k) — Former Employer", institution: "Fidelity", balance: 385_000, positions: [
            Position(symbol: "FXAIX", name: "Fidelity 500 Index Fund", value: 328_950, assetClass: "us_equity", accountId: "acct_401k", price: 215, qty: 1530),
            Position(symbol: "FXNAX", name: "Fidelity US Bond Index Fund", value: 56_021, assetClass: "bond", accountId: "acct_401k", price: 10.55, qty: 5310),
        ]),
        Account(id: "acct_rh", name: "Brokerage", institution: "Robinhood", balance: 96_000, positions: [
            Position(symbol: "NVDA", name: "NVIDIA Corp.", value: 52_080, assetClass: "us_equity", accountId: "acct_rh", price: 168, qty: 310, costBasis: 13_472, averageCostBasis: 43.46, unrealizedGain: 38_608, longTermUnrealizedGain: 35_136, shortTermUnrealizedGain: 3_472),
            Position(symbol: "TSLA", name: "Tesla Inc.", value: 24_890, assetClass: "us_equity", accountId: "acct_rh", price: 262, qty: 95, costBasis: 5_529, averageCostBasis: 58.2, unrealizedGain: 19_361, longTermUnrealizedGain: 19_361, shortTermUnrealizedGain: 0),
            Position(symbol: "PLTR", name: "Palantir Technologies", value: 18_848, assetClass: "us_equity", accountId: "acct_rh", price: 124, qty: 152, costBasis: 1_497, averageCostBasis: 9.85, unrealizedGain: 17_351, longTermUnrealizedGain: 17_351, shortTermUnrealizedGain: 0),
            Position(symbol: "CASH", name: "Cash", value: 182, assetClass: "cash", accountId: "acct_rh", price: 182, qty: 1),
        ]),
    ]

    static var allPositions: [Position] { accountsInvested.flatMap { $0.positions } }

    // Asset-class metadata (label + color + one-line description), matching AllocationCard.
    static let classMeta: [String: (label: String, color: Color, blurb: String)] = [
        "us_equity": ("US stocks", .chartNightBlue, "Part of the growth side of your 60/40 plan — built for long-term appreciation."),
        "intl_equity": ("International stocks", .chartSky, "Diversification beyond the US — different economies, different cycles."),
        "bond": ("Bonds", .chartGold, "The income side of your 60/40 plan — ballast when stocks wobble."),
        "muni_bond": ("Municipal bonds", .chartEvergreen, "Tax-advantaged income, a fit for a taxable account like yours."),
        "cash": ("Cash", .chartLightGray, "Dry powder and near-term spending — safe, liquid, low return."),
    ]

    // Net-worth trajectory (dashboard.json netWorthHistory)
    static let netWorth = 2_746_000
    static let netWorthChange = "+$70,405 (+2.7%) past year"
    static let netWorthHistory: [Double] = [
        2_567_595, 2_603_000, 2_641_000, 2_627_000, 2_669_000, 2_701_000,
        2_690_000, 2_712_000, 2_729_000, 2_718_000, 2_738_000, 2_746_000,
    ]

    // Spending months for the nudge detail (spending.json)
    struct SpendMonth: Identifiable { let id = UUID(); let month: String; let total: Int }
    static let spendMonths: [SpendMonth] = [
        .init(month: "Apr", total: 16_100),
        .init(month: "May", total: 16_901),
        .init(month: "Jun", total: 16_500),
    ]
    static let spendPlan = 14_000
    static let spendAvg3mo = 16_500
    static let spendingBody =
        "Your last three months averaged $16,500/mo against a $14,000/mo plan — about 18% over. Travel and Gifts/Family account for most of the difference. At this pace it's worth checking what it means for the lake house timeline."
    static let nvdaBody =
        "NVIDIA Corp. makes up about 54% of your Robinhood account ($52,080). Single positions this large can swing the whole account. There are ways to reduce concentration over time — some more tax-aware than others."
    static let tslaBody =
        "Tesla Inc. makes up about 26% of your Robinhood account ($24,890). Single positions this large can swing the whole account. There are ways to reduce concentration over time — some more tax-aware than others."

    static func classHoldings(_ key: String) -> [Position] {
        allPositions.filter { $0.assetClass == key }.sorted { $0.value > $1.value }
    }
    static func classTotal(_ key: String) -> Int {
        classHoldings(key).reduce(0) { $0 + $1.value }
    }
    static var investedTotal: Int { allPositions.reduce(0) { $0 + $1.value } }

    static func account(_ id: String) -> Account? {
        accountsInvested.first { $0.id == id }
    }

    // A tappable asset class (drives ClassDetailSheet via .sheet(item:)).
    struct ClassRef: Identifiable { let id: String }

    // Unified nudge model — powers both the Home attention rows / Wealth insight
    // cards and the tapped-in NudgeDetailSheet (matches dashboard.json nudges).
    struct NudgeInfo: Identifiable {
        let id: String
        let kind: Kind
        let icon: String
        let severity: Sev
        let title: String       // list + hero title
        let sub: String         // list subtitle
        let headline: String    // hero metric, e.g. "18% over plan"
        let body: String
        let cta: String
        var concentrationPct: Int? = nil
        enum Kind { case spending, concentration, heldAway }
        enum Sev {
            case attention, info
            var color: Color { self == .attention ? .attention : .allworthAccent }
            var label: String { self == .attention ? "Attention" : "Insight" }
        }
    }

    static let homeNudges: [NudgeInfo] = [
        NudgeInfo(id: "spending", kind: .spending, icon: "chart.line.uptrend.xyaxis", severity: .attention,
                  title: "Spending is running above plan", sub: "18% over plan",
                  headline: "18% over plan", body: spendingBody, cta: "Ask me what this means"),
        NudgeInfo(id: "nvda", kind: .concentration, icon: "chart.pie", severity: .info,
                  title: "NVDA is a large share of your Robinhood account", sub: "54% of the account",
                  headline: "54% of the account", body: nvdaBody, cta: "Ask me about my options", concentrationPct: 54),
        NudgeInfo(id: "tsla", kind: .concentration, icon: "chart.pie", severity: .info,
                  title: "TSLA is a large share of your Robinhood account", sub: "26% of the account",
                  headline: "26% of the account", body: tslaBody, cta: "Ask me about my options", concentrationPct: 26),
        NudgeInfo(id: "heldaway", kind: .heldAway, icon: "wallet.bifold", severity: .info,
                  title: "Money held outside your plan", sub: "$611,000 held away — worth a conversation",
                  headline: "$611,000 held away",
                  body: "We can see $611,000 in accounts held away from your Allworth plan — a 401(k), a brokerage, and cash. Linking them lets Nicole plan around everything you own, so decisions on taxes and risk account for the whole picture.",
                  cta: "Complete your picture"),
    ]

    static var wealthConcentration: [NudgeInfo] { homeNudges.filter { $0.kind == .concentration } }
}
