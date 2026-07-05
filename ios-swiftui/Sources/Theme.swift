import SwiftUI

// Brand tokens ported 1:1 from the RN app's src/theme.ts, which in turn comes
// from ALW001_01_Brand_Dashboard_DEC2024.pdf (the brand source of truth).
// Keep this file in lockstep with theme.ts so the two apps never drift.

extension Color {
    init(hex: UInt, alpha: Double = 1) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: alpha
        )
    }

    // Primary palette
    static let allworthNavy = Color(hex: 0x173D67)   // Indigo Blue — wordmark, filled actions
    static let allworthAccent = Color(hex: 0x3E71B7) // Cerulean — Iris, links, advisor presence
    static let nightBlue = Color(hex: 0x0C2E4E)      // Night Blue — premium hero surface

    // Neutrals
    static let surfacePrimary = Color(hex: 0xF3F4F4) // Feather Gray — screen background
    static let ice = Color(hex: 0xEDF2F7)

    // Ink
    static let inkPrimary = Color(hex: 0x000000)
    static let inkSecondary = Color(hex: 0x595959)
    static let inkTertiary = Color(hex: 0x828282)
    static let hairline = Color(hex: 0xE6E6E6)
    static let inkFaint = Color(hex: 0xE6E6E6)

    // Money / semantic (mapped onto the secondary palette)
    static let gain = Color(hex: 0x436434)      // Evergreen
    static let loss = Color(hex: 0xD26D37)      // Pumpkin
    static let attention = Color(hex: 0xD26D37) // Pumpkin

    // Secondary palette — charts/infographics only (brand deck p.7)
    static let chartNightBlue = Color(hex: 0x0C2E4E)
    static let chartSky = Color(hex: 0x289FDA)
    static let chartEvergreen = Color(hex: 0x436434)
    static let chartGold = Color(hex: 0xA99C6C)
    static let chartLightGray = Color(hex: 0xBEBEBE)
}

// "$1,663,363" — negatives render as "-$310,000" (mirror of theme.ts usd()).
func usd(_ n: Int) -> String {
    let f = NumberFormatter()
    f.numberStyle = .decimal
    f.groupingSeparator = ","
    let s = f.string(from: NSNumber(value: abs(n))) ?? String(abs(n))
    return (n < 0 ? "-$" : "$") + s
}

// Playfair Display for display/headings, Lato for body — the two brand faces.
// PostScript names verified from the bundled TTFs.
enum BrandFont {
    static func display(_ size: CGFloat) -> Font { .custom("PlayfairDisplay-Bold", size: size) }
    static func displayMedium(_ size: CGFloat) -> Font { .custom("PlayfairDisplay-SemiBold", size: size) }
    static func displayItalic(_ size: CGFloat) -> Font { .custom("PlayfairDisplay-SemiBoldItalic", size: size) }
    static func sans(_ size: CGFloat) -> Font { .custom("Lato-Regular", size: size) }
    static func sansBold(_ size: CGFloat) -> Font { .custom("Lato-Bold", size: size) }
    static func sansItalic(_ size: CGFloat) -> Font { .custom("Lato-Italic", size: size) }
}

// 4pt spacing scale — snap paddings/gaps to these, like the RN `space` token.
enum Space {
    static let s1: CGFloat = 4
    static let s2: CGFloat = 8
    static let s3: CGFloat = 12
    static let s4: CGFloat = 16
    static let s5: CGFloat = 20
    static let s6: CGFloat = 24
    static let s8: CGFloat = 32
}

enum Radius {
    static let chip: CGFloat = 10
    static let card: CGFloat = 16
    static let hero: CGFloat = 28
}
