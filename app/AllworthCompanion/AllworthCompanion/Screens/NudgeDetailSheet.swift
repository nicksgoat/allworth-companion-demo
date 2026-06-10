import SwiftUI

struct NudgeDetailSheet: View {
    let nudge: Nudge
    @Environment(AppState.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var spending: SpendingDetail?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(nudge.title).sectionHeaderStyle()
                    Text(nudge.headline)
                        .font(Theme.number(44, weight: .semibold))
                        .foregroundStyle(Theme.attention)
                }
                .padding(.top, 24)

                Text(nudge.body)
                    .font(Theme.body)
                    .lineSpacing(5)
                    .foregroundStyle(Theme.inkPrimary)

                if nudge.type == "spending", let s = spending {
                    spendingBars(s)
                }

                Button {
                    app.chatPrefill = chatPrompt
                    app.selectedTab = .chat
                    dismiss()
                } label: {
                    Label(nudge.cta, systemImage: "bubble.left.and.text.bubble.right")
                        .font(Theme.body.weight(.semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(Theme.allworthAccent, in: .rect(cornerRadius: 12, style: .continuous))
                        .foregroundStyle(.white)
                }
                .buttonStyle(.plain)

                AdvisorHandoffCard()
                DisclaimerFooter()
            }
            .padding(20)
        }
        .background(Theme.surfacePrimary)
        .task {
            if nudge.type == "spending" {
                spending = try? await app.api.spending(clientId: app.clientId)
            }
        }
    }

    private var chatPrompt: String {
        switch nudge.type {
        case "spending": "I know we've been spending more the last few months — what does that actually mean for my plan?"
        case "concentration": "What are my options for the concentrated position you flagged?"
        default: nudge.cta
        }
    }

    /// "2026-04" → "Apr"
    private func monthName(_ month: String) -> String {
        guard let m = Int(month.suffix(2)), (1...12).contains(m) else { return String(month.suffix(2)) }
        return Calendar.current.shortMonthSymbols[m - 1]
    }

    private func spendingBars(_ s: SpendingDetail) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Last \(s.months.count) months vs plan").sectionHeaderStyle()
            ForEach(s.months) { month in
                HStack(spacing: 10) {
                    Text(monthName(month.month))
                        .font(Theme.number(13))
                        .foregroundStyle(Theme.inkTertiary)
                        .frame(width: 30, alignment: .leading)
                    GeometryReader { geo in
                        ZStack(alignment: .leading) {
                            Capsule().fill(Theme.inkPrimary.opacity(0.05))
                            Capsule()
                                .fill(month.total > month.planned ? Theme.attention : Theme.allworthNavy)
                                .frame(width: geo.size.width * min(1, CGFloat(month.total) / CGFloat(month.planned) / 1.4))
                        }
                    }
                    .frame(height: 8)
                    Text(month.total.usd)
                        .font(Theme.number(13))
                        .monospacedDigit()
                        .foregroundStyle(Theme.inkSecondary)
                        .frame(width: 64, alignment: .trailing)
                }
            }
            Text("Plan: \(s.plan.usd)/mo · Recent average: \(s.avg3mo.usd)/mo")
                .font(Theme.caption)
                .foregroundStyle(Theme.inkTertiary)
        }
    }
}
