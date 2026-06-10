import SwiftUI

struct ProfileView: View {
    @Environment(AppState.self) private var app
    @State private var facts: [LearnedFact] = []

    private static let categoryLabels: [String: String] = [
        "goals": "Your goals",
        "preferences": "Your preferences",
        "concerns": "On your mind",
        "liquidity_events": "Decisions in motion",
        "outside_assets_mentioned": "Accounts you've mentioned",
        "life_events": "Life events",
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("What I've learned")
                        .font(Theme.title)
                        .foregroundStyle(Theme.inkPrimary)
                    Text("Every fact has a source, a timestamp, and an audit trail. Nothing here came from anywhere but you.")
                        .font(Theme.secondary)
                        .foregroundStyle(Theme.inkSecondary)
                }
                .padding(.top, 8)

                ForEach(groupedCategories, id: \.self) { category in
                    VStack(alignment: .leading, spacing: 0) {
                        Text(Self.categoryLabels[category] ?? category)
                            .sectionHeaderStyle()
                            .padding(.bottom, 4)
                        let categoryFacts = facts.filter { $0.category == category }
                        ForEach(Array(categoryFacts.enumerated()), id: \.element.id) { index, fact in
                            if index > 0 { HairlineDivider() }
                            LearnedFactRow(fact: fact)
                        }
                    }
                }

                if facts.isEmpty {
                    Text("Nothing learned yet — start a conversation.")
                        .font(Theme.secondary)
                        .foregroundStyle(Theme.inkTertiary)
                        .padding(.top, 40)
                        .frame(maxWidth: .infinity)
                }

                DisclaimerFooter().padding(.vertical, 8)
            }
            .padding(20)
        }
        .background(Theme.surfacePrimary)
        .task { await load() }
        .refreshable { await load() }
    }

    private var groupedCategories: [String] {
        var seen: [String] = []
        for fact in facts where !seen.contains(fact.category) {
            seen.append(fact.category)
        }
        return seen
    }

    private func load() async {
        if let response = try? await app.api.profile(clientId: app.clientId) {
            facts = response.facts
        }
    }
}
