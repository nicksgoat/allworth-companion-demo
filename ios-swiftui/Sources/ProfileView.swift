import SwiftUI

// Profile — navy identity hero (centered avatar + name), then the advisor, the
// ways to reach them, and what the assistant has learned. Static copy.
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
                            VStack(alignment: .leading, spacing: Space.s3) {
                                SectionHeader("Your advisor")
                                HStack(spacing: Space.s3) {
                                    ZStack {
                                        Circle().fill(Color.allworthNavy).frame(width: 48, height: 48)
                                        Text(Demo.advisorInitials).font(BrandFont.sansBold(16)).foregroundStyle(.white)
                                    }
                                    VStack(alignment: .leading, spacing: 1) {
                                        Text(Demo.advisorName).font(BrandFont.sansBold(16)).foregroundStyle(Color.inkPrimary)
                                        Text(Demo.advisorTitle).font(BrandFont.sans(13)).foregroundStyle(Color.inkSecondary)
                                    }
                                    Spacer()
                                    CircleIconButton(icon: "bubble.left.fill")
                                }
                                .padding(Space.s4)
                                .card()
                            }
                            .entrance(0.2, appeared: appeared)

                            VStack(spacing: Space.s3) {
                                linkRow("calendar", "Book a meeting or request a topic")
                                linkRow("flag", "Your goals")
                                linkRow("folder", "Documents")
                            }
                            .entrance(0.3, appeared: appeared)

                            DisclaimerFooter().entrance(0.4, appeared: appeared)
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

    private func identityHero(safeTop: CGFloat) -> some View {
        NavyHeroBand(safeTop: safeTop) {
            VStack(spacing: 10) {
                ZStack {
                    Circle().fill(Color.white.opacity(0.16)).frame(width: 88, height: 88)
                    Text("MT").font(BrandFont.sansBold(30)).foregroundStyle(.white)
                }
                Text(Demo.clientName).font(BrandFont.displayMedium(30)).foregroundStyle(.white)
                Text(Demo.clientMeta).font(BrandFont.sans(14)).foregroundStyle(.white.opacity(0.7))
            }
            .frame(maxWidth: .infinity)
            .entrance(0.1, appeared: appeared)
        }
    }

    private func linkRow(_ icon: String, _ label: String) -> some View {
        HStack(spacing: Space.s3) {
            Image(systemName: icon).font(.system(size: 18)).foregroundStyle(Color.allworthAccent).frame(width: 22)
            Text(label).font(BrandFont.sansBold(15)).foregroundStyle(Color.inkPrimary)
            Spacer()
            Image(systemName: "chevron.right").font(.system(size: 14, weight: .semibold)).foregroundStyle(Color.inkTertiary)
        }
        .padding(.horizontal, Space.s4)
        .padding(.vertical, Space.s4)
        .card()
    }
}
