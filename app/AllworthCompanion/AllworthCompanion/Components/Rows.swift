import SwiftUI

struct AccountRow: View {
    let account: Account

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(account.name)
                    .font(Theme.body)
                    .foregroundStyle(Theme.inkPrimary)
                Text(account.institution)
                    .font(Theme.caption)
                    .foregroundStyle(Theme.inkTertiary)
            }
            Spacer()
            Text(account.balance.usd)
                .font(Theme.number(17))
                .monospacedDigit()
                .foregroundStyle(account.balance < 0 ? Theme.lossRed : Theme.inkPrimary)
        }
        .padding(.vertical, 12)
    }
}

struct LearnedFactRow: View {
    let fact: LearnedFact

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(fact.fact)
                .font(Theme.body)
                .foregroundStyle(Theme.inkPrimary)
                .fixedSize(horizontal: false, vertical: true)
            if !fact.sourceQuote.isEmpty {
                HStack(alignment: .top, spacing: 8) {
                    RoundedRectangle(cornerRadius: 1)
                        .fill(Theme.hairline)
                        .frame(width: 2)
                    Text("“\(fact.sourceQuote)”")
                        .font(Theme.secondary.italic())
                        .foregroundStyle(Theme.inkSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Text("Learned \(fact.learnedAt.shortDate) · from your conversation")
                .font(Theme.caption)
                .foregroundStyle(Theme.inkTertiary)
        }
        .padding(.vertical, 12)
    }
}

struct HairlineDivider: View {
    var body: some View {
        Rectangle().fill(Theme.hairline).frame(height: 0.5)
    }
}

struct DisclaimerFooter: View {
    var body: some View {
        Text("Educational information, not investment advice. Allworth Financial demo — synthetic data.")
            .font(.system(size: 11))
            .foregroundStyle(Theme.inkTertiary)
            .multilineTextAlignment(.center)
            .frame(maxWidth: .infinity)
    }
}
