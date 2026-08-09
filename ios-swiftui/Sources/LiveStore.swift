import SwiftUI

// Fetches the tab data from the live backend at launch and holds it. Views read
// these when present and fall back to the golden-matched static Demo data when
// the backend is unreachable, so the app always renders.
@Observable final class LiveStore {
    var netWorth: Int?
    var netWorthHistory: [Double] = []
    var spendMonths: [Demo.SpendMonth] = []
    var spendPlan: Int?
    var spendAvg3mo: Int?
    var overPlanPct: Int?
    var loaded = false

    func load() async {
        if let dash: DashboardResponse = try? await APIClient.get("/api/clients/\(APIClient.clientId)/dashboard") {
            netWorth = dash.netWorth
            netWorthHistory = dash.netWorthHistory.map { Double($0.value) }
        }
        if let spend: SpendingResponse = try? await APIClient.get("/api/clients/\(APIClient.clientId)/spending") {
            spendMonths = spend.months.map { Demo.SpendMonth(month: Self.shortMonth($0.month), total: $0.total) }
            spendPlan = spend.plan
            spendAvg3mo = spend.avg3mo
            overPlanPct = spend.overPlanPct
        }
        loaded = true
    }

    private static func shortMonth(_ ym: String) -> String {
        let names = ["01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr", "05": "May", "06": "Jun",
                     "07": "Jul", "08": "Aug", "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec"]
        let parts = ym.split(separator: "-")
        return parts.count == 2 ? (names[String(parts[1])] ?? ym) : ym
    }
}

struct DashboardResponse: Decodable {
    let netWorth: Int
    let netWorthHistory: [HistPoint]
    struct HistPoint: Decodable { let month: String; let value: Int }
}

struct SpendingResponse: Decodable {
    let months: [Month]
    let plan: Int
    let avg3mo: Int
    let overPlanPct: Int
    struct Month: Decodable { let month: String; let total: Int }
}
