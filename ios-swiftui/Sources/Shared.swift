import SwiftUI

// Entrance motion — fade up on arrival. Mirror of the RN `RiseIn` (fade + rise,
// eased out). Drive with an `appeared` flag flipped in `.onAppear`.
extension View {
    func entrance(_ delay: Double, appeared: Bool, rise: CGFloat = 14) -> some View {
        self
            .opacity(appeared ? 1 : 0)
            .offset(y: appeared ? 0 : rise)
            .animation(.easeOut(duration: 0.5).delay(delay), value: appeared)
    }
}

// Full-bleed navy hero band: the premium navy surface reaching the top and side
// edges with a rounded bottom lip. First module on a hero screen; pair with a
// `GlassHeader(onHero:)`. Content is padded to clear the header zone.
struct NavyHeroBand<Content: View>: View {
    let safeTop: CGFloat
    var supergraphic = false
    var breathe = false
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: Space.s3) {
            content()
        }
        .padding(.horizontal, Space.s5)
        .padding(.top, safeTop + 48 + Space.s4)
        .padding(.bottom, Space.s5)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(NavyGradient(supergraphic: supergraphic, breathe: breathe))
        .clipShape(
            UnevenRoundedRectangle(
                bottomLeadingRadius: Radius.hero,
                bottomTrailingRadius: Radius.hero,
                style: .continuous
            )
        )
    }
}

// A navy hero that carries only a title + subtitle (Wealth / Profile / Book).
struct SimpleHero: View {
    let safeTop: CGFloat
    let title: String
    let subtitle: String
    var appeared: Bool
    var centered: Bool = false

    var body: some View {
        NavyHeroBand(safeTop: safeTop) {
            VStack(alignment: centered ? .center : .leading, spacing: 6) {
                Text(title)
                    .font(BrandFont.displayMedium(30))
                    .foregroundStyle(.white)
                Text(subtitle)
                    .font(BrandFont.sans(13))
                    .foregroundStyle(.white.opacity(0.72))
            }
            .frame(maxWidth: .infinity, alignment: centered ? .center : .leading)
            .entrance(0.1, appeared: appeared)
        }
    }
}

// Small round accent button used on cards (advisor row).
struct CircleIconButton: View {
    let icon: String
    var action: () -> Void = {}
    var body: some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 18))
                .foregroundStyle(Color.allworthAccent)
                .frame(width: 38, height: 38)
                .background(Circle().fill(Color.allworthAccent.opacity(0.12)))
        }
        .buttonStyle(.plain)
    }
}
