import SwiftUI

struct NudgeCard: View {
    let nudge: Nudge
    var onTap: () -> Void

    @State private var pulsed = false

    var body: some View {
        Button(action: onTap) {
            HStack(alignment: .top, spacing: 14) {
                Image(systemName: icon)
                    .font(.system(size: 20))
                    .foregroundStyle(Theme.attention)
                    .frame(width: 28)
                    .scaleEffect(pulsed ? 1 : 0.85)
                VStack(alignment: .leading, spacing: 4) {
                    Text(nudge.title)
                        .font(Theme.body.weight(.semibold))
                        .foregroundStyle(Theme.inkPrimary)
                        .multilineTextAlignment(.leading)
                    Text(nudge.headline)
                        .font(Theme.number(15, weight: .semibold))
                        .foregroundStyle(Theme.attention)
                    Text(nudge.cta)
                        .font(Theme.secondary)
                        .foregroundStyle(Theme.allworthAccent)
                        .padding(.top, 2)
                }
                Spacer(minLength: 0)
                Image(systemName: "chevron.right")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(Theme.inkTertiary)
                    .padding(.top, 4)
            }
            .padding(16)
            .cardStyle()
        }
        .buttonStyle(.plain)
        .onAppear {
            withAnimation(Theme.spring.delay(0.3)) { pulsed = true }
        }
    }

    private var icon: String {
        switch nudge.type {
        case "spending": "chart.line.uptrend.xyaxis"
        case "concentration": "chart.pie"
        default: "lightbulb"
        }
    }
}
