import SwiftUI

// MARK: - Scroll tracking

// Reports how far a ScrollView has scrolled (0 at rest, growing as you scroll
// up) — mirror of the RN `scrollY` Animated.Value that drives the header + logo
// handoff. Uses ScrollGeometry (the reliable modern API); apply to the ScrollView.
extension View {
    func trackScroll(into scrollY: Binding<CGFloat>) -> some View {
        onScrollGeometryChange(for: CGFloat.self) { geo in
            geo.contentOffset.y + geo.contentInsets.top
        } action: { _, newValue in
            scrollY.wrappedValue = max(0, newValue)
        }
    }
}

func clamp01(_ v: CGFloat) -> CGFloat { min(1, max(0, v)) }

// MARK: - Card

struct CardBackground: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(Color.white)
            .clipShape(RoundedRectangle(cornerRadius: Radius.card, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: Radius.card, style: .continuous)
                    .stroke(Color.allworthNavy.opacity(0.05), lineWidth: 1)
            )
            .shadow(color: Color.nightBlue.opacity(0.05), radius: 8, x: 0, y: 2)
    }
}

extension View {
    func card() -> some View { modifier(CardBackground()) }
}

// MARK: - Section header

struct SectionHeader: View {
    let text: String
    init(_ text: String) { self.text = text }
    var body: some View {
        Text(text.uppercased())
            .font(BrandFont.sansBold(11))
            .tracking(0.6)
            .foregroundStyle(Color.inkTertiary)
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: - Navy hero gradient

// The brand's premium fill: Night Blue → Indigo vertical gradient + a soft
// cerulean glow in the upper-right. Reserved for hero surfaces (DESIGN.md).
struct NavyGradient: View {
    var body: some View {
        GeometryReader { geo in
            ZStack {
                LinearGradient(
                    colors: [.nightBlue, .allworthNavy],
                    startPoint: .top,
                    endPoint: .bottom
                )
                RadialGradient(
                    colors: [Color.allworthAccent.opacity(0.36), Color.allworthAccent.opacity(0)],
                    center: UnitPoint(x: 0.82, y: 0.12),
                    startRadius: 0,
                    endRadius: max(geo.size.width, geo.size.height) * 0.8
                )
            }
        }
    }
}

// MARK: - Glass header

// THE header (DESIGN.md): brand mark chip + title, one optional action, on glass.
// - onHero:      floats white over the navy hero, cross-fades to light glass on scroll.
// - heroReveal:  Home only — no white row; the hero's big logo is the brand at the
//                top and the compact header simply reveals on scroll.
// - default:     solid light glass, always visible (Chat).
struct GlassHeader: View {
    @Environment(AppModel.self) private var app
    let title: String
    var scrollY: CGFloat = 0
    var onHero: Bool = false
    var heroReveal: Bool = false
    var actionIcon: String? = nil
    var onAction: (() -> Void)? = nil
    let safeTop: CGFloat

    private let barHeight: CGFloat = 48
    private var glassOpacity: CGFloat { onHero ? clamp01(scrollY / 130) : 1 }

    var body: some View {
        ZStack(alignment: .bottom) {
            // Glass material (fades in over the hero; always on elsewhere).
            Rectangle()
                .fill(.ultraThinMaterial)
                .overlay(Color.surfacePrimary.opacity(0.55))
                .overlay(alignment: .bottom) { Divider().opacity(0.5) }
                .opacity(glassOpacity)

            // Dark row (ink on light) — the resolved/scrolled state.
            row(light: false)
                .opacity(onHero ? glassOpacity : 1)

            // White row over the navy hero (skipped in heroReveal mode).
            if onHero && !heroReveal {
                row(light: true)
                    .opacity(1 - glassOpacity)
                    .allowsHitTesting(false)
            }
        }
        .frame(height: safeTop + barHeight)
        .frame(maxWidth: .infinity)
        .ignoresSafeArea(edges: .top)
    }

    private func row(light: Bool) -> some View {
        let ink = light ? Color.white : Color.inkPrimary
        let mark = light ? Color.white : Color.allworthNavy
        let chip = light ? Color.white.opacity(0.16) : Color.white.opacity(0.85)
        return HStack(spacing: Space.s2) {
            ZStack {
                RoundedRectangle(cornerRadius: Radius.chip, style: .continuous)
                    .fill(chip)
                    .frame(width: 32, height: 32)
                AllworthMark(color: mark, size: 18)
            }
            .contentShape(Rectangle())
            .onTapGesture(count: 3) { app.showDemoControls = true }
            Text(title)
                .font(BrandFont.sansBold(17))
                .foregroundStyle(ink)
            Spacer(minLength: 0)
            if let icon = actionIcon {
                Button(action: { onAction?() }) {
                    Image(systemName: icon)
                        .font(.system(size: 20))
                        .foregroundStyle(ink)
                        .frame(width: 36, height: 36)
                }
            } else {
                Color.clear.frame(width: 36, height: 36)
            }
        }
        .padding(.horizontal, Space.s4)
        .frame(height: barHeight)
    }
}

// MARK: - Disclaimer

struct DisclaimerFooter: View {
    var body: some View {
        Text("Educational information, not investment advice. Allworth Financial demo — synthetic data.")
            .font(BrandFont.sans(11))
            .foregroundStyle(Color.inkTertiary)
            .multilineTextAlignment(.center)
            .frame(maxWidth: .infinity)
            .padding(.vertical, Space.s2)
    }
}
