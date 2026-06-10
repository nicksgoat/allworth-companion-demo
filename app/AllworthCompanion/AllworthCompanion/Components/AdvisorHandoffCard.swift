import SwiftUI

/// The most important recurring component: every analytical answer and nudge
/// ends here. Designed once, reused everywhere.
struct AdvisorHandoffCard: View {
    var advisorName = "Dana Whitfield"
    var advisorInitials = "DW"
    var advisorTitle = "Senior Financial Advisor, CFP®"

    @State private var sent = false

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 12) {
                Circle()
                    .fill(Theme.allworthNavy)
                    .frame(width: 44, height: 44)
                    .overlay {
                        Text(advisorInitials)
                            .font(.system(size: 16, weight: .semibold, design: .rounded))
                            .foregroundStyle(.white)
                    }
                VStack(alignment: .leading, spacing: 2) {
                    Text("Bring this to \(advisorName.split(separator: " ").first.map(String.init) ?? advisorName)")
                        .font(Theme.body.weight(.semibold))
                        .foregroundStyle(Theme.inkPrimary)
                    Text(advisorTitle)
                        .font(Theme.caption)
                        .foregroundStyle(Theme.inkSecondary)
                }
                Spacer()
            }
            if sent {
                Label("Flagged for your next session with Dana", systemImage: "checkmark.circle.fill")
                    .font(Theme.secondary)
                    .foregroundStyle(Theme.allworthAccent)
                    .transition(.opacity)
            } else {
                HStack(spacing: 10) {
                    handoffButton("Message", filled: true)
                    handoffButton("Schedule", filled: false)
                }
            }
        }
        .padding(16)
        .cardStyle()
        .sensoryFeedback(.success, trigger: sent)
    }

    private func handoffButton(_ label: String, filled: Bool) -> some View {
        Button {
            withAnimation(Theme.spring) { sent = true }
        } label: {
            Text(label)
                .font(Theme.secondary.weight(.semibold))
                .frame(maxWidth: .infinity)
                .padding(.vertical, 10)
                .background(filled ? Theme.allworthAccent : Theme.allworthAccent.opacity(0.12),
                            in: .rect(cornerRadius: 10, style: .continuous))
                .foregroundStyle(filled ? .white : Theme.allworthAccent)
        }
        .buttonStyle(.plain)
    }
}

#Preview {
    AdvisorHandoffCard()
        .padding(20)
        .background(Theme.surfacePrimary)
}
