import SwiftUI

// Profile — 1:1 port of the RN ProfileScreen: navy identity hero, the advisor
// block (card + three link rows → concierge / goals / documents), the two
// summary-first collapsible cards (What I've learned / Meeting notes, expanding
// to the real fact groups + note rows, each tapping into its detail sheet), the
// Demo advisor-switch row, disclaimer, and the account/sign-out footer.
struct ProfileView: View {
    @State private var scrollY: CGFloat = 0
    @State private var appeared = false

    @State private var selectedFact: Demo.LearnedFact?
    @State private var selectedFactCategory = ""
    @State private var selectedNote: Demo.MeetingNote?
    @State private var conciergeOpen = false
    @State private var goalsOpen = false
    @State private var documentsOpen = false

    var body: some View {
        GeometryReader { proxy in
            let safeTop = proxy.safeAreaInsets.top
            ZStack(alignment: .top) {
                Color.surfacePrimary.ignoresSafeArea()

                ScrollView(showsIndicators: false) {
                    VStack(spacing: 0) {
                        identityHero(safeTop: safeTop)

                        VStack(spacing: Space.s6) {
                            advisorBlock
                            learnedCard
                            notesCard
                            demoBlock
                            DisclaimerFooter()
                            accountFooter
                        }
                        .padding(.horizontal, Space.s5)
                        .padding(.top, Space.s6)
                        .padding(.bottom, Space.s8)
                    }
                }
                .trackScroll(into: $scrollY)
                .ignoresSafeArea(edges: .top)

                GlassHeader(title: "Profile", scrollY: scrollY, onHero: true, safeTop: safeTop)
            }
        }
        .onAppear { appeared = true; autoPresent() }
        .sheet(item: $selectedFact) { f in
            FactDetailSheet(fact: f, categoryLabel: selectedFactCategory) { selectedFact = nil }
        }
        .sheet(item: $selectedNote) { n in
            MeetingNoteDetailSheet(note: n) { selectedNote = nil }
        }
        .sheet(isPresented: $conciergeOpen) { AdvisorConciergeSheet { conciergeOpen = false } }
        .sheet(isPresented: $goalsOpen) { GoalsSheet { goalsOpen = false } }
        .sheet(isPresented: $documentsOpen) { DocumentsSheet { documentsOpen = false } }
    }

    // Debug-only: SIMCTL_CHILD_AUTO_SHEET=<name> auto-presents a sheet for the
    // screenshot verify loop (simctl has no tap input). No-op in normal use.
    private func autoPresent() {
        switch ProcessInfo.processInfo.environment["AUTO_SHEET"] {
        case "fact": selectedFactCategory = Demo.factGroups[0].label; selectedFact = Demo.factGroups[0].facts.first
        case "note": selectedNote = Demo.meetingNotes.first
        case "documents": documentsOpen = true
        case "goals": goalsOpen = true
        case "concierge": conciergeOpen = true
        default: break
        }
    }

    // MARK: identity hero

    private func identityHero(safeTop: CGFloat) -> some View {
        NavyHeroBand(safeTop: safeTop) {
            VStack(spacing: 10) {
                ZStack {
                    Circle().fill(Color.white.opacity(0.16)).frame(width: 76, height: 76)
                    Text("MT").font(BrandFont.sansBold(28)).tracking(0.5).foregroundStyle(.white)
                }
                Text(Demo.clientName).font(BrandFont.displayMedium(27)).foregroundStyle(.white)
                Text(Demo.clientCityAge).font(BrandFont.sans(14)).foregroundStyle(.white.opacity(0.7))
            }
            .frame(maxWidth: .infinity)
            .entrance(0.1, appeared: appeared)
        }
    }

    // MARK: advisor block

    private var advisorBlock: some View {
        VStack(alignment: .leading, spacing: Space.s2) {
            SectionHeader("Your advisor")
            HStack(spacing: Space.s3) {
                ZStack {
                    Circle().fill(Color.allworthNavy).frame(width: 46, height: 46)
                    Text(Demo.advisorInitials).font(BrandFont.sansBold(15)).tracking(0.5).foregroundStyle(.white)
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text(Demo.advisorName).font(BrandFont.sansBold(16)).foregroundStyle(Color.inkPrimary)
                    Text(Demo.advisorTitle).font(BrandFont.sans(13)).foregroundStyle(Color.inkSecondary)
                }
                Spacer(minLength: Space.s2)
                Image(systemName: "ellipsis.message.fill")
                    .font(.system(size: 18))
                    .foregroundStyle(Color.allworthAccent)
                    .frame(width: 40, height: 40)
                    .background(Circle().fill(Color.allworthAccent.opacity(0.12)))
            }
            .padding(14)
            .card()

            linkRow("calendar", "Book a meeting or request a topic") { conciergeOpen = true }
            linkRow("flag", "Your goals") { goalsOpen = true }
            linkRow("folder", "Documents") { documentsOpen = true }
        }
        .entrance(0.2, appeared: appeared)
    }

    private func linkRow(_ icon: String, _ label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: Space.s3) {
                Image(systemName: icon).font(.system(size: 18)).foregroundStyle(Color.allworthAccent).frame(width: 22)
                Text(label).font(BrandFont.sansBold(14)).foregroundStyle(Color.inkPrimary)
                Spacer()
                Image(systemName: "chevron.right").font(.system(size: 15, weight: .semibold)).foregroundStyle(Color.inkTertiary)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .card()
        }
        .buttonStyle(.plain)
    }

    // MARK: collapsible cards (expand to the real content)

    private var learnedCard: some View {
        CollapsibleCardView(icon: "sparkles", title: "What I've learned · \(Demo.allFacts.count)", preview: Demo.learnedPreview) {
            VStack(alignment: .leading, spacing: 2) {
                ForEach(Demo.factGroups) { group in
                    Text(group.label).font(BrandFont.sansBold(13)).foregroundStyle(Color.inkSecondary)
                        .padding(.top, 6).padding(.bottom, 2)
                    ForEach(Array(group.facts.enumerated()), id: \.element.id) { i, fact in
                        if i > 0 { Hairline() }
                        Button {
                            selectedFactCategory = group.label
                            selectedFact = fact
                        } label: { LearnedFactRowView(fact: fact) }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        .entrance(0.3, appeared: appeared)
    }

    private var notesCard: some View {
        CollapsibleCardView(icon: "doc.text", title: "Meeting notes · \(Demo.meetingNotes.count)", preview: "Latest: \(Demo.meetingNotes[0].title)") {
            VStack(alignment: .leading, spacing: 2) {
                ForEach(Array(Demo.meetingNotes.enumerated()), id: \.element.id) { i, note in
                    if i > 0 { Hairline() }
                    Button { selectedNote = note } label: { MeetingNoteRowView(note: note) }
                        .buttonStyle(.plain)
                }
            }
        }
        .entrance(0.36, appeared: appeared)
    }

    // MARK: demo block

    private var demoBlock: some View {
        VStack(alignment: .leading, spacing: Space.s2) {
            SectionHeader("Demo")
            HStack(spacing: Space.s3) {
                Image(systemName: "person.2").font(.system(size: 18)).foregroundStyle(Color.allworthAccent).frame(width: 22)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Switch to advisor view").font(BrandFont.sansBold(14)).foregroundStyle(Color.inkPrimary)
                    Text("See \(Demo.advisorFirst)'s book and live client conversations")
                        .font(BrandFont.sans(12)).foregroundStyle(Color.inkTertiary)
                }
                Spacer(minLength: Space.s2)
                Image(systemName: "chevron.right").font(.system(size: 15, weight: .semibold)).foregroundStyle(Color.inkTertiary)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .card()
        }
        .entrance(0.42, appeared: appeared)
    }

    // MARK: account footer

    private var accountFooter: some View {
        VStack(spacing: Space.s3) {
            Text(Demo.userEmail).font(BrandFont.sans(13)).foregroundStyle(Color.inkTertiary)
            Text("Sign out")
                .font(BrandFont.sansBold(14))
                .foregroundStyle(Color.inkSecondary)
                .padding(.horizontal, Space.s6)
                .padding(.vertical, 10)
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.hairline, lineWidth: 1))
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, Space.s2)
        .overlay(alignment: .top) { Rectangle().fill(Color.hairline).frame(height: 1) }
        .entrance(0.48, appeared: appeared)
    }
}

// Summary-first collapsible card (RN CollapsibleCard) — collapsed shows a 2-line
// preview; expanded reveals the real content.
struct CollapsibleCardView<Content: View>: View {
    let icon: String
    let title: String
    let preview: String
    @ViewBuilder var content: () -> Content
    @State private var expanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: Space.s3) {
            Button {
                withAnimation(.easeOut(duration: 0.2)) { expanded.toggle() }
            } label: {
                HStack(spacing: Space.s2) {
                    Image(systemName: icon).font(.system(size: 13)).foregroundStyle(Color.allworthAccent)
                    Text(title.uppercased()).font(BrandFont.sansBold(11)).tracking(0.6).foregroundStyle(Color.inkTertiary)
                    Spacer()
                    Image(systemName: expanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 13)).foregroundStyle(Color.inkTertiary)
                }
            }
            .buttonStyle(.plain)

            if expanded {
                content()
            } else {
                Text(preview)
                    .font(BrandFont.sans(15))
                    .foregroundStyle(Color.inkPrimary)
                    .lineSpacing(5)
                    .lineLimit(2)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(Space.s4)
        .card()
    }
}

// MARK: - Rows (RN Rows.tsx)

struct LearnedFactRowView: View {
    let fact: Demo.LearnedFact
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(fact.fact).font(BrandFont.sans(17)).foregroundStyle(Color.inkPrimary).lineSpacing(6)
                .frame(maxWidth: .infinity, alignment: .leading)
            HStack(alignment: .top, spacing: 8) {
                RoundedRectangle(cornerRadius: 1).fill(Color.hairline).frame(width: 2)
                Text("“\(fact.quote)”").font(BrandFont.sansItalic(15)).foregroundStyle(Color.inkSecondary).lineSpacing(6)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .fixedSize(horizontal: false, vertical: true)
            Text("Learned \(fact.learned) · from your conversation")
                .font(BrandFont.sans(13)).foregroundStyle(Color.inkTertiary)
        }
        .padding(.vertical, 12)
        .contentShape(Rectangle())
    }
}

struct MeetingNoteRowView: View {
    let note: Demo.MeetingNote
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text(note.title).font(BrandFont.sansBold(16)).foregroundStyle(Color.inkPrimary)
                Spacer(minLength: 0)
                Text(note.date).font(BrandFont.sans(13)).foregroundStyle(Color.inkTertiary)
            }
            Text(note.summary).font(BrandFont.sans(15)).foregroundStyle(Color.inkSecondary).lineSpacing(4).lineLimit(2)
                .frame(maxWidth: .infinity, alignment: .leading)
            Text("With \(note.advisor)").font(BrandFont.sans(13)).foregroundStyle(Color.inkTertiary)
        }
        .padding(.vertical, 12)
        .contentShape(Rectangle())
    }
}
