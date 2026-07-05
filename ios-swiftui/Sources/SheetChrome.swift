import SwiftUI

// Shared sheet furniture — the light SheetHeader (section-label title + close
// chip) from RN Rows.tsx, the hairline divider, and the smoothed line/area chart
// used by the net-worth and position detail sheets.

// MARK: - Sheet header (light)

struct SheetHeaderView: View {
    let title: String
    let onClose: () -> Void
    var body: some View {
        HStack(spacing: Space.s3) {
            SectionHeader(title)
            Button(action: onClose) {
                ZStack {
                    Circle().fill(Color.inkFaint).frame(width: 30, height: 30)
                    Image(systemName: "xmark")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(Color.inkSecondary)
                }
            }
            .buttonStyle(.plain)
        }
    }
}

struct Hairline: View {
    var body: some View { Rectangle().fill(Color.hairline).frame(height: 1) }
}

// MARK: - Smoothed line/area chart

// Catmull-Rom → Bézier so the coarse monthly anchors read as one organic curve,
// the way densify() does in the RN chart. `lineColor`/`fillTop` let the same
// shape serve the white-on-navy net-worth chart and the tinted sparkline.
struct SmoothChart: View {
    let values: [Double]
    var lineColor: Color = .white
    var lineWidth: CGFloat = 3
    var fillTop: Color = Color.white.opacity(0.18)
    var fillBottom: Color = Color.white.opacity(0)
    var showBaseline: Bool = true
    var showEndDot: Bool = true
    var haloOpacity: Double = 0.12

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width, h = geo.size.height
            let pts = points(in: CGSize(width: w, height: h))
            if pts.count >= 2 {
                let line = smoothPath(pts)
                let area = areaPath(from: line, w: w, h: h)

                area.fill(LinearGradient(colors: [fillTop, fillBottom], startPoint: .top, endPoint: .bottom))
                if showBaseline {
                    Path { p in
                        p.move(to: CGPoint(x: 0, y: pts[0].y))
                        p.addLine(to: CGPoint(x: w, y: pts[0].y))
                    }
                    .stroke(lineColor.opacity(0.4), style: StrokeStyle(lineWidth: 1, dash: [2, 6]))
                }
                line.stroke(lineColor.opacity(haloOpacity), style: StrokeStyle(lineWidth: lineWidth + 5, lineCap: .round, lineJoin: .round))
                line.stroke(lineColor, style: StrokeStyle(lineWidth: lineWidth, lineCap: .round, lineJoin: .round))
                if showEndDot, let last = pts.last {
                    Circle().fill(lineColor.opacity(0.2)).frame(width: 16, height: 16).position(last)
                    Circle().fill(lineColor).frame(width: 8, height: 8).position(last)
                }
            }
        }
    }

    private func points(in size: CGSize) -> [CGPoint] {
        guard values.count >= 2 else { return [] }
        let lo = values.min() ?? 0, hi = values.max() ?? 1
        let pad = (hi - lo) / 6 == 0 ? 1 : (hi - lo) / 6
        let yMin = lo - pad, yMax = hi + pad
        return values.enumerated().map { i, v in
            let x = CGFloat(i) / CGFloat(values.count - 1) * size.width
            let y = size.height - CGFloat((v - yMin) / (yMax - yMin)) * size.height
            return CGPoint(x: x, y: y)
        }
    }

    private func smoothPath(_ p: [CGPoint]) -> Path {
        var path = Path()
        path.move(to: p[0])
        for i in 0..<p.count - 1 {
            let p0 = i == 0 ? p[0] : p[i - 1]
            let p1 = p[i], p2 = p[i + 1]
            let p3 = i + 2 < p.count ? p[i + 2] : p2
            let c1 = CGPoint(x: p1.x + (p2.x - p0.x) / 6, y: p1.y + (p2.y - p0.y) / 6)
            let c2 = CGPoint(x: p2.x - (p3.x - p1.x) / 6, y: p2.y - (p3.y - p1.y) / 6)
            path.addCurve(to: p2, control1: c1, control2: c2)
        }
        return path
    }

    private func areaPath(from line: Path, w: CGFloat, h: CGFloat) -> Path {
        var a = line
        a.addLine(to: CGPoint(x: w, y: h))
        a.addLine(to: CGPoint(x: 0, y: h))
        a.closeSubpath()
        return a
    }
}

// A deterministic per-symbol series ending at the position's value — stands in
// for the seeded synthetic positionHistory(). Labeled "illustrative" in the UI.
func syntheticSeries(seed: String, end: Double, count: Int) -> [Double] {
    let h = abs(seed.hashValue)
    var vals: [Double] = []
    let drift = 0.72 + Double(h % 40) / 100.0        // 0.72–1.12 of end at the start
    for i in 0..<count {
        let t = Double(i) / Double(count - 1)
        let base = end * (drift + (1 - drift) * t)
        let wiggle = sin(Double(i) * 1.7 + Double(h % 10)) * end * 0.012
        vals.append(base + wiggle)
    }
    vals[count - 1] = end
    return vals
}
