import SwiftUI

// The Allworth "Iris" mark, drawn as a radial sunburst. This is a faithful
// approximation of the official symbol (a circular burst derived from the Iris
// geometry) — the real vector logo from the Allworth marketing team should
// replace it before anything ships. Two lengths of ray alternate, like the deck.
struct AllworthMark: View {
    var color: Color = .allworthAccent
    var size: CGFloat = 28
    var rays: Int = 24

    var body: some View {
        Canvas { ctx, sz in
            let c = CGPoint(x: sz.width / 2, y: sz.height / 2)
            let inner = sz.width * 0.13
            let longR = sz.width * 0.48
            let shortR = sz.width * 0.36
            let lw = max(1, sz.width * 0.045)
            for i in 0..<rays {
                let a = (Double(i) / Double(rays)) * 2 * Double.pi - Double.pi / 2
                let outer = (i % 2 == 0) ? longR : shortR
                var p = Path()
                p.move(to: CGPoint(x: c.x + CGFloat(cos(a)) * inner, y: c.y + CGFloat(sin(a)) * inner))
                p.addLine(to: CGPoint(x: c.x + CGFloat(cos(a)) * outer, y: c.y + CGFloat(sin(a)) * outer))
                ctx.stroke(p, with: .color(color), style: StrokeStyle(lineWidth: lw, lineCap: .round))
            }
        }
        .frame(width: size, height: size)
    }
}

// The horizontal lockup: Iris mark + "Allworth" wordmark + "FINANCIAL" descender.
// `light` renders it all white for navy hero surfaces. `scale` sizes the whole
// lockup relative to the ~150pt Home-hero treatment.
struct AllworthWordmark: View {
    var light: Bool = false
    var scale: CGFloat = 1

    var body: some View {
        let ink = light ? Color.white : Color.allworthNavy
        HStack(spacing: 9 * scale) {
            AllworthMark(color: ink, size: 34 * scale)
            VStack(alignment: .leading, spacing: 1 * scale) {
                Text("Allworth")
                    .font(BrandFont.sansBold(29 * scale))
                    .tracking(-0.4 * scale)
                    .foregroundStyle(ink)
                Text("FINANCIAL")
                    .font(BrandFont.sansBold(9 * scale))
                    .tracking(5 * scale)
                    .foregroundStyle(ink.opacity(0.92))
                    .padding(.leading, 1 * scale)
            }
        }
    }
}
