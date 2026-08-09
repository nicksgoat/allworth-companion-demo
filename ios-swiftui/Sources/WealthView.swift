import SwiftUI

// Wealth — 1:1 port of the RN InvestScreen: navy band (with a Net-worth tap into
// the full navy detail), the managed/held-away/liabilities breakdown, the
// Overview/Holdings segment, the allocation donut + legend (tap → class detail),
// advisor handoff, concentration insights (tap → nudge detail), complete-your-
// picture, automatic investing, and — under Holdings — the real per-account
// sections (tap a position → position detail).
struct WealthView: View {
    @State private var scrollY: CGFloat = 0
    @State private var appeared = false
    @State private var segment = "Overview"

    @State private var netWorthOpen = false
    @State private var selectedNudge: Demo.NudgeInfo?
    @State private var selectedClass: Demo.ClassRef?
    @State private var selectedPosition: Demo.Position?

    var body: some View {
        GeometryReader { proxy in
            let safeTop = proxy.safeAreaInsets.top
            ZStack(alignment: .top) {
                Color.surfacePrimary.ignoresSafeArea()

                ScrollView(showsIndicators: false) {
                    VStack(spacing: 0) {
                        band(safeTop: safeTop)

                        VStack(spacing: Space.s6) {
                            BreakdownCard(managed: Demo.managed, heldAway: Demo.heldAway, liabilities: Demo.liabilities)
                                .entrance(0.16, appeared: appeared)

                            SegmentedControl(options: ["Overview", "Holdings"], selected: $segment)
                                .entrance(0.22, appeared: appeared)

                            if segment == "Overview" {
                                overview
                            } else {
                                holdings
                            }

                            DisclaimerFooter()
                        }
                        .padding(.horizontal, Space.s5)
                        .padding(.top, Space.s6)
                        .padding(.bottom, Space.s8)
                    }
                }
                .trackScroll(into: $scrollY)
                .ignoresSafeArea(edges: .top)

                GlassHeader(title: "Your wealth", scrollY: scrollY, onHero: true, safeTop: safeTop)
            }
        }
        .onAppear { appeared = true; autoPresent() }
        .fullScreenCover(isPresented: $netWorthOpen) {
            NetWorthDetailSheet { netWorthOpen = false }
        }
        .sheet(item: $selectedNudge) { n in
            NudgeDetailSheet(nudge: n) { selectedNudge = nil }
        }
        .sheet(item: $selectedClass) { c in
            ClassDetailSheet(key: c.id) { selectedClass = nil }
        }
        .sheet(item: $selectedPosition) { p in
            PositionDetailSheet(position: p) { selectedPosition = nil }
        }
    }

    // Debug-only: SIMCTL_CHILD_AUTO_SHEET=<name> auto-presents a sheet so the
    // verify loop can screenshot it (simctl has no tap input). No-op in normal use.
    private func autoPresent() {
        switch ProcessInfo.processInfo.environment["AUTO_SHEET"] {
        case "networth": netWorthOpen = true
        case "nudge": selectedNudge = Demo.homeNudges.first
        case "class": selectedClass = Demo.ClassRef(id: "us_equity")
        case "position": selectedPosition = Demo.account("acct_trust")?.positions.first
        case "holdings": segment = "Holdings"
        default: break
        }
    }

    private func band(safeTop: CGFloat) -> some View {
        NavyHeroBand(safeTop: safeTop) {
            VStack(alignment: .leading, spacing: Space.s3) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Where your money lives").font(BrandFont.displayMedium(26)).foregroundStyle(.white)
                    Text("\(Demo.accountCount) accounts — managed, held away, and owed.")
                        .font(BrandFont.sans(13)).foregroundStyle(.white.opacity(0.82))
                }
                Button { netWorthOpen = true } label: {
                    HStack(spacing: 3) {
                        Text("Net worth").font(BrandFont.sansBold(14)).foregroundStyle(.white.opacity(0.92))
                        Image(systemName: "chevron.right").font(.system(size: 12, weight: .semibold)).foregroundStyle(.white.opacity(0.92))
                    }
                    .padding(.top, 2)
                }
                .buttonStyle(.plain)
            }
            .entrance(0.1, appeared: appeared)
        }
    }

    private var overview: some View {
        VStack(spacing: Space.s6) {
            VStack(alignment: .leading, spacing: Space.s3) {
                SectionHeader("Your allocation")
                AllocationCard { key in selectedClass = Demo.ClassRef(id: key) }
                AdvisorHandoffCard()
            }
            ForEach(Demo.wealthConcentration) { n in
                NudgeCard(nudge: n) { selectedNudge = n }
            }
            CompletePictureCard()
            RecurringCard()
        }
    }

    private var holdings: some View {
        VStack(spacing: Space.s3) {
            ForEach(Array(Demo.accountsInvested.enumerated()), id: \.element.id) { i, account in
                AccountHoldingsSection(account: account, onSelect: { selectedPosition = $0 }, expanded: i == 0)
            }
        }
    }
}
