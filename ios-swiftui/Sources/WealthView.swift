import SwiftUI

// Wealth — navy hero + the structure of the money (no combined total at screen
// level; that lives in a tapped-in detail, per DESIGN.md). Structural copy.
struct WealthView: View {
    @State private var scrollY: CGFloat = 0
    @State private var appeared = false

    private let accounts: [(String, String, String)] = [
        ("Allworth Managed", "Brokerage · Advisory", "chart.line.uptrend.xyaxis"),
        ("Allworth IRA", "Retirement", "building.columns"),
        ("Robinhood", "Held away", "wallet.pass"),
        ("Chase Checking", "Cash", "banknote"),
    ]

    var body: some View {
        GeometryReader { proxy in
            let safeTop = proxy.safeAreaInsets.top
            ZStack(alignment: .top) {
                Color.surfacePrimary.ignoresSafeArea()
                ScrollView(showsIndicators: false) {
                    VStack(spacing: 0) {
                        SimpleHero(safeTop: safeTop, title: "Your wealth",
                                   subtitle: "Where your money lives · 4 accounts", appeared: appeared)
                        VStack(spacing: Space.s6) {
                            VStack(alignment: .leading, spacing: Space.s3) {
                                SectionHeader("Accounts")
                                VStack(spacing: 0) {
                                    ForEach(Array(accounts.enumerated()), id: \.offset) { i, a in
                                        if i > 0 { Divider().background(Color.hairline) }
                                        HStack(spacing: Space.s3) {
                                            ZStack {
                                                RoundedRectangle(cornerRadius: Radius.chip, style: .continuous)
                                                    .fill(Color.ice).frame(width: 34, height: 34)
                                                Image(systemName: a.2).font(.system(size: 15)).foregroundStyle(Color.allworthNavy)
                                            }
                                            VStack(alignment: .leading, spacing: 2) {
                                                Text(a.0).font(BrandFont.sansBold(15)).foregroundStyle(Color.inkPrimary)
                                                Text(a.1).font(BrandFont.sans(12)).foregroundStyle(Color.inkSecondary)
                                            }
                                            Spacer()
                                            Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold)).foregroundStyle(Color.inkTertiary)
                                        }
                                        .padding(.vertical, Space.s3)
                                    }
                                }
                                .padding(.horizontal, Space.s4)
                                .padding(.vertical, Space.s1)
                                .card()
                            }
                            .entrance(0.2, appeared: appeared)

                            DisclaimerFooter().entrance(0.3, appeared: appeared)
                        }
                        .padding(.horizontal, Space.s5)
                        .padding(.top, Space.s6)
                        .padding(.bottom, Space.s8)
                    }
                }
                .trackScroll(into: $scrollY)
                .ignoresSafeArea(edges: .top)

                GlassHeader(title: "Wealth", scrollY: scrollY, onHero: true, safeTop: safeTop)
            }
        }
        .onAppear { appeared = true }
    }
}
