import SwiftUI

// The official Allworth "Iris" symbol, rendered from the marketing team's vector
// paths (ACCENT_PATHS) — nine tapering petals radiating around a center ring.
// `color` tints the whole mark (accent by default, white on navy surfaces).
struct AllworthMark: View {
    var color: Color = .allworthAccent
    var size: CGFloat = 28

    var body: some View {
        SVGPaths(paths: AllworthLogoArt.accentPaths, viewBox: AllworthLogoArt.markViewBox)
            .fill(color)
            .frame(width: size, height: size)
    }
}

// The primary horizontal lockup: Iris + "Allworth" logotype + "FINANCIAL", drawn
// from the official logo vectors so the wordmark matches the brand exactly.
// `light` renders it all white for navy hero surfaces; `scale` sizes it.
struct AllworthWordmark: View {
    var light: Bool = false
    var scale: CGFloat = 1

    private let baseWidth: CGFloat = 156   // scale 1 ≈ the old lockup footprint

    var body: some View {
        let vb = AllworthLogoArt.logoViewBox
        let w = baseWidth * scale
        ZStack {
            SVGPaths(paths: AllworthLogoArt.navyPaths, viewBox: vb)
                .fill(light ? Color.white : Color.allworthNavy)
            SVGPaths(paths: AllworthLogoArt.accentPaths, viewBox: vb)
                .fill(light ? Color.white : Color.allworthAccent)
        }
        .frame(width: w, height: w * vb.height / vb.width)
    }
}
