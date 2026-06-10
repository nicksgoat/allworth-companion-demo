import SwiftUI

enum Theme {
    // Brand — verified 2026-06-09 from allworth-financial-logo-color.svg
    static let allworthNavy = Color(hex: 0x173D67)
    static let allworthAccent = Color(hex: 0x3E71B7)

    // Surfaces
    static let surfacePrimary = Color(hex: 0xFAFAF8)
    static let surfaceCard = Color.white

    // Ink hierarchy
    static let inkPrimary = Color(hex: 0x0B1220)
    static let inkSecondary = Color(hex: 0x0B1220).opacity(0.60)
    static let inkTertiary = Color(hex: 0x0B1220).opacity(0.38)
    static let hairline = Color(hex: 0x0B1220).opacity(0.08)

    // Semantic only — money movement, never decorative
    static let gainGreen = Color(hex: 0x00C805)
    static let lossRed = Color(hex: 0xCF3A4A)
    static let attention = Color(hex: 0xC77B17)

    // Type scale: hero 48 / title 28 / body 17 / secondary 15 / caption 13
    static let hero = Font.system(size: 48, weight: .semibold, design: .rounded)
    static let title = Font.system(size: 28, weight: .semibold)
    static let body = Font.system(size: 17)
    static let secondary = Font.system(size: 15)
    static let caption = Font.system(size: 13)
    static func number(_ size: CGFloat, weight: Font.Weight = .medium) -> Font {
        .system(size: size, weight: weight, design: .rounded)
    }

    // One spring app-wide
    static let spring = Animation.spring(response: 0.35, dampingFraction: 0.8)

    static let cardRadius: CGFloat = 16
}

extension View {
    /// The one card style: white, continuous 16pt radius, the one shadow.
    func cardStyle() -> some View {
        background(Theme.surfaceCard, in: .rect(cornerRadius: Theme.cardRadius, style: .continuous))
            .shadow(color: .black.opacity(0.05), radius: 12, y: 4)
    }

    /// 11pt ALL-CAPS tertiary section header treatment.
    func sectionHeaderStyle() -> some View {
        font(.system(size: 11, weight: .semibold))
            .textCase(.uppercase)
            .tracking(0.6)
            .foregroundStyle(Theme.inkTertiary)
    }
}

extension Color {
    init(hex: UInt32) {
        self.init(
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255
        )
    }
}

extension Int {
    /// "$2,746,000" — negatives render as "-$310,000"
    var usd: String {
        let f = NumberFormatter()
        f.numberStyle = .decimal
        f.maximumFractionDigits = 0
        let s = f.string(from: NSNumber(value: abs(self))) ?? "\(abs(self))"
        return (self < 0 ? "-$" : "$") + s
    }
}

extension String {
    /// "2026-06-08T19:14:00Z" → "Jun 8"
    var shortDate: String {
        guard let date = ISO8601DateFormatter().date(from: self)
            ?? ISO8601DateFormatter().date(from: self + "T00:00:00Z") else { return self }
        return date.formatted(.dateTime.month(.abbreviated).day())
    }
}
