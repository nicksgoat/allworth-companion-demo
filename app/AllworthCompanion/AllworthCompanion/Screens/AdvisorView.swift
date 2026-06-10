import SwiftUI

struct AdvisorView: View {
    @Environment(AppState.self) private var app
    @State private var book: BookResponse?
    @State private var autoDetail = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Your book")
                                .font(Theme.title)
                                .foregroundStyle(Theme.inkPrimary)
                            if let advisor = book?.advisor {
                                Text("\(advisor.name) · \(advisor.title)")
                                    .font(Theme.caption)
                                    .foregroundStyle(Theme.inkSecondary)
                            }
                        }
                        Spacer()
                        AllworthWordmark()
                    }
                    .padding(.top, 8)

                    if let book {
                        VStack(alignment: .leading, spacing: 0) {
                            ForEach(Array(book.households.enumerated()), id: \.element.id) { index, household in
                                if index > 0 { HairlineDivider() }
                                NavigationLink {
                                    AdvisorClientDetail(household: household)
                                } label: {
                                    HouseholdRow(household: household)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    } else {
                        ProgressView().frame(maxWidth: .infinity).padding(.top, 80)
                    }

                    DisclaimerFooter().padding(.vertical, 8)
                }
                .padding(20)
            }
            .background(Theme.surfacePrimary)
            .toolbar(.hidden, for: .navigationBar)
            .navigationDestination(isPresented: $autoDetail) {
                if let maya = book?.households.first(where: { $0.clientId == "maya" }) {
                    AdvisorClientDetail(household: maya)
                }
            }
        }
        .task {
            book = try? await app.api.book(advisorId: "dana")
            if ProcessInfo.processInfo.environment["DEMO_SCREEN"] == "advisor_detail" {
                autoDetail = true
            }
        }
    }
}

private struct HouseholdRow: View {
    let household: Household

    var body: some View {
        HStack(spacing: 12) {
            Circle()
                .fill(household.highlight == true ? Theme.allworthNavy : Theme.inkPrimary.opacity(0.08))
                .frame(width: 40, height: 40)
                .overlay {
                    Text(household.name.split(separator: " ").compactMap(\.first).prefix(2).map(String.init).joined())
                        .font(.system(size: 14, weight: .semibold, design: .rounded))
                        .foregroundStyle(household.highlight == true ? .white : Theme.inkSecondary)
                }
            VStack(alignment: .leading, spacing: 3) {
                Text(household.name)
                    .font(Theme.body.weight(household.highlight == true ? .semibold : .regular))
                    .foregroundStyle(Theme.inkPrimary)
                HStack(spacing: 8) {
                    Text("\(household.managedAssets.usd) managed")
                        .font(Theme.caption)
                        .foregroundStyle(Theme.inkTertiary)
                    if household.heldAwayDetected > 0 {
                        Text("\(household.heldAwayDetected.usd) held away")
                            .font(Theme.caption.weight(.medium))
                            .foregroundStyle(Theme.allworthAccent)
                    }
                }
            }
            Spacer()
            if household.openNudges > 0 {
                Text("\(household.openNudges)")
                    .font(Theme.number(13, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(width: 22, height: 22)
                    .background(Theme.attention, in: Circle())
            }
            Image(systemName: "chevron.right")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(Theme.inkTertiary)
        }
        .padding(.vertical, 12)
    }
}

struct AdvisorClientDetail: View {
    let household: Household
    @Environment(AppState.self) private var app
    @State private var brief: AdvisorBrief?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                if let brief {
                    VStack(alignment: .leading, spacing: 4) {
                        HeroNumberView(label: "Held away — detected", value: brief.heldAwayDetected)
                        Text("alongside \(brief.managedTotal.usd) managed")
                            .font(Theme.number(15))
                            .foregroundStyle(Theme.inkSecondary)
                    }

                    VStack(alignment: .leading, spacing: 0) {
                        Text("Outside accounts").sectionHeaderStyle().padding(.bottom, 4)
                        ForEach(Array((brief.heldAwayAccounts + brief.liabilities).enumerated()), id: \.element.id) { index, account in
                            if index > 0 { HairlineDivider() }
                            AccountRow(account: account)
                        }
                    }

                    VStack(alignment: .leading, spacing: 10) {
                        HStack(spacing: 6) {
                            Image(systemName: "sparkles")
                                .font(.system(size: 12))
                                .foregroundStyle(Theme.allworthAccent)
                            Text("Auto-prepared brief").sectionHeaderStyle()
                        }
                        ForEach(brief.narrative.split(separator: "\n").map(String.init), id: \.self) { paragraph in
                            Text(paragraph)
                                .font(Theme.secondary)
                                .lineSpacing(4)
                                .foregroundStyle(Theme.inkPrimary)
                        }
                    }
                    .padding(16)
                    .cardStyle()

                    if !brief.openNudges.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Open nudges").sectionHeaderStyle()
                            ForEach(brief.openNudges) { nudge in
                                HStack(spacing: 10) {
                                    Circle().fill(Theme.attention).frame(width: 6, height: 6)
                                    Text(nudge.title)
                                        .font(Theme.secondary)
                                        .foregroundStyle(Theme.inkPrimary)
                                    Spacer()
                                    Text(nudge.headline)
                                        .font(Theme.number(13, weight: .semibold))
                                        .foregroundStyle(Theme.attention)
                                }
                                .padding(.vertical, 6)
                            }
                        }
                    }

                    if !brief.profile.isEmpty {
                        VStack(alignment: .leading, spacing: 0) {
                            Text("What the assistant has learned").sectionHeaderStyle().padding(.bottom, 4)
                            ForEach(Array(brief.profile.prefix(4).enumerated()), id: \.element.id) { index, fact in
                                if index > 0 { HairlineDivider() }
                                LearnedFactRow(fact: fact)
                            }
                        }
                    }
                } else {
                    ProgressView().frame(maxWidth: .infinity).padding(.top, 100)
                }
                DisclaimerFooter().padding(.vertical, 8)
            }
            .padding(20)
        }
        .background(Theme.surfacePrimary)
        .navigationTitle(household.name)
        .navigationBarTitleDisplayMode(.inline)
        .task {
            brief = try? await app.api.brief(advisorId: "dana", clientId: household.clientId)
        }
    }
}
