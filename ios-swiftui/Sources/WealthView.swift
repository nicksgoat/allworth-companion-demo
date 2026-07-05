import SwiftUI

// Wealth — 1:1 port of the RN InvestScreen (Overview): navy band, the
// managed/held-away/liabilities breakdown, the Overview/Holdings segment, the
// allocation donut + legend, advisor handoff, concentration insights, the
// complete-your-picture card, and automatic investing. Compliance-shaped: no
// combined total at screen level (that lives in the tapped-in Net worth detail).
struct WealthView: View {
    @State private var scrollY: CGFloat = 0
    @State private var appeared = false
    @State private var segment = "Overview"

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
        .onAppear { appeared = true }
    }

    private func band(safeTop: CGFloat) -> some View {
        NavyHeroBand(safeTop: safeTop) {
            VStack(alignment: .leading, spacing: Space.s3) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Where your money lives").font(BrandFont.displayMedium(26)).foregroundStyle(.white)
                    Text("\(Demo.accountCount) accounts — managed, held away, and owed.")
                        .font(BrandFont.sans(13)).foregroundStyle(.white.opacity(0.82))
                }
                HStack(spacing: 3) {
                    Text("Net worth").font(BrandFont.sansBold(14)).foregroundStyle(.white.opacity(0.92))
                    Image(systemName: "chevron.right").font(.system(size: 12, weight: .semibold)).foregroundStyle(.white.opacity(0.92))
                }
                .padding(.top, 2)
            }
            .entrance(0.1, appeared: appeared)
        }
    }

    private var overview: some View {
        VStack(spacing: Space.s6) {
            VStack(alignment: .leading, spacing: Space.s3) {
                SectionHeader("Your allocation")
                AllocationCard()
                AdvisorHandoffCard()
            }
            ForEach(Demo.concentration) { n in
                NudgeCard(nudge: n)
            }
            CompletePictureCard()
            RecurringCard()
        }
    }

    private var holdings: some View {
        VStack(alignment: .leading, spacing: Space.s3) {
            ForEach(Array(Demo.allocation.enumerated()), id: \.element.id) { _, c in
                HStack(spacing: Space.s3) {
                    RoundedRectangle(cornerRadius: 3).fill(c.color).frame(width: 5, height: 34)
                    Text(c.label).font(BrandFont.sansBold(15)).foregroundStyle(Color.inkPrimary)
                    Spacer()
                    Text(usd(c.value)).font(BrandFont.sansBold(15)).foregroundStyle(Color.inkPrimary).monospacedDigit()
                }
                .padding(14)
                .card()
            }
        }
    }
}
