import SwiftUI

struct DashboardView: View {
    @Environment(AppState.self) private var app
    @State private var selectedNudge: Nudge?

    var body: some View {
        ScrollView {
            if let d = app.dashboard {
                content(d)
            } else if let error = app.dashboardError {
                errorState(error)
            } else {
                skeleton
            }
        }
        .background(Theme.surfacePrimary)
        .task {
            if app.dashboard == nil { await app.loadDashboard() }
            if ProcessInfo.processInfo.environment["DEMO_SCREEN"] == "nudge" {
                selectedNudge = app.dashboard?.nudges.first
            }
        }
        .refreshable { await app.loadDashboard() }
        .sheet(item: $selectedNudge) { nudge in
            NudgeDetailSheet(nudge: nudge)
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
        }
    }

    private func content(_ d: Dashboard) -> some View {
        VStack(alignment: .leading, spacing: 24) {
            HStack {
                Text("Good evening, \(d.client?.name.split(separator: " ").first.map(String.init) ?? "Maya")")
                    .font(Theme.title)
                    .foregroundStyle(Theme.inkPrimary)
                Spacer()
                AllworthWordmark()
            }
            .padding(.top, 8)

            VStack(alignment: .leading, spacing: 14) {
                HeroNumberView(label: "Net worth", value: d.netWorth, delta: monthDelta(d))
                SparklineChart(points: d.netWorthHistory)
            }

            ForEach(d.nudges.prefix(2)) { nudge in
                NudgeCard(nudge: nudge) { selectedNudge = nudge }
            }

            accountSection("Allworth accounts", accounts: d.accounts.allworth, total: d.allworthTotal)
            accountSection("Outside accounts we can see",
                           accounts: d.accounts.outside,
                           total: d.heldAwayTotal,
                           caption: "\(d.heldAwayTotal.usd) held away")

            DisclaimerFooter().padding(.vertical, 8)
        }
        .padding(20)
    }

    private func accountSection(_ header: String, accounts: [Account], total: Int, caption: String? = nil) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(header).sectionHeaderStyle()
                Spacer()
                if let caption {
                    Text(caption)
                        .font(Theme.number(13))
                        .foregroundStyle(Theme.inkSecondary)
                }
            }
            .padding(.bottom, 4)
            ForEach(Array(accounts.enumerated()), id: \.element.id) { index, account in
                if index > 0 { HairlineDivider() }
                AccountRow(account: account)
            }
        }
    }

    private func monthDelta(_ d: Dashboard) -> (String, Bool)? {
        guard d.netWorthHistory.count >= 2 else { return nil }
        let last = d.netWorthHistory[d.netWorthHistory.count - 1].value
        let prev = d.netWorthHistory[d.netWorthHistory.count - 2].value
        let diff = last - prev
        return ("\(diff >= 0 ? "+" : "")\(diff.usd) this month", diff >= 0)
    }

    private var skeleton: some View {
        VStack(alignment: .leading, spacing: 20) {
            ForEach(0..<5, id: \.self) { _ in
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(Theme.inkPrimary.opacity(0.05))
                    .frame(height: 72)
            }
        }
        .padding(20)
        .shimmering()
    }

    private func errorState(_ message: String) -> some View {
        ContentUnavailableView {
            Label("Backend offline", systemImage: "antenna.radiowaves.left.and.right.slash")
        } description: {
            Text(message)
        } actions: {
            Button("Retry") { Task { await app.loadDashboard() } }
                .buttonStyle(.borderedProminent)
        }
        .padding(.top, 120)
    }
}

private struct Shimmer: ViewModifier {
    @State private var phase: CGFloat = -1

    func body(content: Content) -> some View {
        content
            .opacity(0.7 + 0.3 * Double(phase))
            .onAppear {
                withAnimation(.easeInOut(duration: 0.9).repeatForever(autoreverses: true)) { phase = 1 }
            }
    }
}

extension View {
    func shimmering() -> some View { modifier(Shimmer()) }
}
