import SwiftUI

// Profile — 1:1 port of the RN ProfileScreen: navy identity hero, the advisor
// block (card + three link rows), the two summary-first collapsible cards
// (What I've learned / Meeting notes), the Demo advisor-switch row, disclaimer,
// and the account/sign-out footer.
struct ProfileView: View {
    @State private var scrollY: CGFloat = 0
    @State private var appeared = false

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
        .onAppear { appeared = true }
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

    // MARK: advisor block (section header + card + 3 link rows, tight 8pt gaps)

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

            linkRow("calendar", "Book a meeting or request a topic")
            linkRow("flag", "Your goals")
            linkRow("folder", "Documents")
        }
        .entrance(0.2, appeared: appeared)
    }

    private func linkRow(_ icon: String, _ label: String) -> some View {
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

    // MARK: collapsible summary cards (rendered collapsed, matching first paint)

    private var learnedCard: some View {
        CollapsibleCardView(
            icon: "sparkles",
            title: "What I've learned · \(Demo.factsCount)",
            preview: Demo.learnedPreview
        )
        .entrance(0.3, appeared: appeared)
    }

    private var notesCard: some View {
        CollapsibleCardView(
            icon: "doc.text",
            title: "Meeting notes · \(Demo.notesCount)",
            preview: "Latest: \(Demo.latestNote)"
        )
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

// Summary-first collapsible card (RN CollapsibleCard) — icon + section-label
// title + chevron, with a two-line preview. Tapping expands; here it renders
// collapsed to match the screen's first paint.
struct CollapsibleCardView: View {
    let icon: String
    let title: String
    let preview: String
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

            Text(preview)
                .font(BrandFont.sans(15))
                .foregroundStyle(Color.inkPrimary)
                .lineSpacing(5)
                .lineLimit(expanded ? nil : 2)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(Space.s4)
        .card()
    }
}
