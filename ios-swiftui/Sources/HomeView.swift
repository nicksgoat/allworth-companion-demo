import SwiftUI

// Home — the front door. Big Allworth logo "hello" that hands off to the header
// mark on scroll, then a calm cascade of: what needs attention, quick actions,
// the advisor, and the way into Wealth. No totals here (they live in Wealth).
struct HomeView: View {
    @State private var scrollY: CGFloat = 0
    @State private var appeared = false
    @State private var sheetNudge: Demo.NudgeInfo?

    var body: some View {
        GeometryReader { proxy in
            let safeTop = proxy.safeAreaInsets.top

            ZStack(alignment: .top) {
                Color.surfacePrimary.ignoresSafeArea()

                ScrollView(showsIndicators: false) {
                    VStack(spacing: 0) {
                        hero(safeTop: safeTop)

                        VStack(spacing: Space.s6) {
                            attention.entrance(0.24, appeared: appeared)
                            quickActions.entrance(0.34, appeared: appeared)
                            advisor.entrance(0.44, appeared: appeared)
                            wealthGuide.entrance(0.54, appeared: appeared)
                            DisclaimerFooter().entrance(0.6, appeared: appeared)
                        }
                        .padding(.horizontal, Space.s5)
                        .padding(.top, Space.s6)
                        .padding(.bottom, Space.s8)
                    }
                }
                .trackScroll(into: $scrollY)
                .ignoresSafeArea(edges: .top)

                GlassHeader(title: "Home", scrollY: scrollY, onHero: true, heroReveal: true, safeTop: safeTop)
            }
        }
        .onAppear { appeared = true }
        .sheet(item: $sheetNudge) { n in
            NudgeDetailSheet(nudge: n) { sheetNudge = nil }
        }
    }

    // MARK: hero

    private func hero(safeTop: CGFloat) -> some View {
        let t = clamp01(scrollY / 90)             // logo handoff progress
        let logoOpacity = 1 - t
        let logoScale = 1 - 0.18 * t              // 1 → 0.82
        let logoLift = -10 * t

        return NavyHeroBand(safeTop: safeTop) {
            AllworthWordmark(light: true)
                .scaleEffect(logoScale, anchor: .topLeading)
                .offset(y: logoLift)
                .opacity(appeared ? logoOpacity : 0)
                .offset(y: appeared ? 0 : 8)
                .animation(.easeOut(duration: 0.56), value: appeared)
                .padding(.bottom, Space.s1)

            VStack(alignment: .leading, spacing: Space.s3) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("\(Demo.greetingForNow()),")
                        .font(BrandFont.sans(14))
                        .foregroundStyle(.white.opacity(0.72))
                    Text(Demo.clientFirstName)
                        .font(BrandFont.displayMedium(30))
                        .foregroundStyle(.white)
                }
                HStack(spacing: 6) {
                    Image(systemName: "person.crop.circle")
                        .font(.system(size: 15))
                        .foregroundStyle(.white.opacity(0.72))
                    Text(Demo.advisorLine)
                        .font(BrandFont.sans(13))
                        .foregroundStyle(.white.opacity(0.82))
                }
                HStack(spacing: 3) {
                    Text("View your wealth")
                        .font(BrandFont.sansBold(14))
                        .foregroundStyle(.white.opacity(0.92))
                    Image(systemName: "chevron.right")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(.white.opacity(0.92))
                }
                .padding(.top, 2)
            }
            .entrance(0.15, appeared: appeared)
        }
    }

    // MARK: sections

    private var attention: some View {
        VStack(alignment: .leading, spacing: Space.s3) {
            SectionHeader("Needs your attention")
            VStack(spacing: 0) {
                ForEach(Array(Demo.homeNudges.enumerated()), id: \.element.id) { i, nudge in
                    if i > 0 { Divider().background(Color.hairline) }
                    AttentionRow(nudge: nudge)
                        .contentShape(Rectangle())
                        .onTapGesture { sheetNudge = nudge }
                }
            }
            .padding(.horizontal, Space.s4)
            .padding(.vertical, Space.s1)
            .card()
        }
    }

    private var quickActions: some View {
        VStack(alignment: .leading, spacing: Space.s3) {
            SectionHeader("Quick actions")
            LazyVGrid(
                columns: [GridItem(.flexible(), spacing: Space.s3), GridItem(.flexible(), spacing: Space.s3)],
                spacing: Space.s3
            ) {
                ForEach(Demo.quickActions) { a in
                    HStack(spacing: Space.s2) {
                        Image(systemName: a.icon).font(.system(size: 18)).foregroundStyle(Color.allworthNavy)
                        Text(a.label).font(BrandFont.sansBold(14)).foregroundStyle(Color.allworthNavy).lineLimit(1)
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, Space.s3)
                    .padding(.vertical, Space.s3)
                    .frame(maxWidth: .infinity)
                    .card()
                }
            }
        }
    }

    private var advisor: some View {
        VStack(alignment: .leading, spacing: Space.s3) {
            SectionHeader("Your advisor")
            HStack(spacing: Space.s3) {
                ZStack {
                    Circle().fill(Color.allworthNavy).frame(width: 44, height: 44)
                    Text(Demo.advisorInitials).font(BrandFont.sansBold(15)).foregroundStyle(.white)
                }
                VStack(alignment: .leading, spacing: 1) {
                    Text(Demo.advisorName).font(BrandFont.sansBold(16)).foregroundStyle(Color.inkPrimary)
                    Text(Demo.advisorTitle).font(BrandFont.sans(13)).foregroundStyle(Color.inkSecondary)
                }
                Spacer(minLength: Space.s2)
                CircleIconButton(icon: "bubble.left.fill")
                CircleIconButton(icon: "calendar")
            }
            .padding(Space.s4)
            .card()
        }
    }

    private var wealthGuide: some View {
        HStack(spacing: Space.s3) {
            Image(systemName: "chart.pie").font(.system(size: 18)).foregroundStyle(Color.allworthAccent)
            VStack(alignment: .leading, spacing: 2) {
                Text("Your wealth").font(BrandFont.sansBold(15)).foregroundStyle(Color.inkPrimary)
                Text("Accounts, allocation, and what's held away")
                    .font(BrandFont.sans(12)).foregroundStyle(Color.inkTertiary)
            }
            Spacer(minLength: Space.s2)
            Image(systemName: "chevron.right").font(.system(size: 14, weight: .semibold)).foregroundStyle(Color.inkTertiary)
        }
        .padding(.horizontal, Space.s4)
        .padding(.vertical, Space.s4)
        .card()
    }
}

struct AttentionRow: View {
    let nudge: Demo.NudgeInfo
    var body: some View {
        let tint = nudge.severity == .attention ? Color.attention : Color.allworthAccent
        HStack(spacing: Space.s3) {
            ZStack {
                RoundedRectangle(cornerRadius: Radius.chip, style: .continuous)
                    .fill(tint.opacity(0.10))
                    .frame(width: 34, height: 34)
                Image(systemName: nudge.icon).font(.system(size: 16)).foregroundStyle(tint)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(nudge.title)
                    .font(BrandFont.sansBold(15))
                    .foregroundStyle(Color.inkPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                Text(nudge.sub).font(BrandFont.sans(12)).foregroundStyle(Color.inkSecondary)
            }
            Spacer(minLength: Space.s2)
            Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold)).foregroundStyle(Color.inkTertiary)
        }
        .padding(.vertical, Space.s3)
    }
}
