import SwiftUI

// Inline chat tool-result widgets — 1:1 port of components/ChatToolWidget.tsx.
// The backend streams the structured tool result on `tool_end`; we route by the
// result's SHAPE (not tool name) into three cards: Monte-Carlo projection (fan
// chart), rebalance (Now→Target allocation), and live goal funding.

// MARK: - Models (shapes the backend streams)

enum ToolWidget: Identifiable {
    case projection(ProjectionResult)
    case rebalance(RebalanceResult)
    case goals(GoalFundingResult)

    var id: String {
        switch self {
        case .projection: return "projection"
        case .rebalance: return "rebalance"
        case .goals: return "goals"
        }
    }

    // Route by result shape, exactly like the RN dispatcher.
    static func from(_ result: [String: Any]?) -> ToolWidget? {
        guard let result, let data = try? JSONSerialization.data(withJSONObject: result) else { return nil }
        let dec = JSONDecoder()
        if result["goals"] != nil, result["summary"] is String,
           let g = try? dec.decode(GoalFundingResult.self, from: data) { return .goals(g) }
        if result["pathSnapshots"] != nil, result["successRate"] != nil,
           let p = try? dec.decode(ProjectionResult.self, from: data) { return .projection(p) }
        if result["trades"] != nil, result["target_allocation"] != nil,
           let r = try? dec.decode(RebalanceResult.self, from: data) { return .rebalance(r) }
        return nil
    }
}

struct ProjectionResult: Decodable {
    struct Snap: Decodable { let age: Int; let median: Double; let p5: Double; let p25: Double; let p75: Double; let p95: Double }
    let pathSnapshots: [Snap]
    let successRate: Double
    let simulations: Int?
    let interpretation: String?
    let assumptions: Assumptions?
    struct Assumptions: Decodable {
        let startingPortfolio: Double?
        let annualDraw: Double?
        let annualSpending: Double?
        let equityAllocation: Double?
        let endAge: Int?
    }
}

struct RebalanceResult: Decodable {
    struct Trade: Decodable { let ticker: String; let action: String; let amount: Double }
    let trades: [Trade]
    let target_allocation: [String: Double]
    let post_trade_allocation: [String: Double]?
    let total_portfolio_value: Double?
    let estimated_tax: Tax?
    struct Tax: Decodable { let total: Double? }
}

struct GoalFundingResult: Decodable {
    let goals: [APIGoal]
    let summary: String
    let assumedGrowthRate: Double?
}

func usdCompact(_ n: Double) -> String {
    let a = abs(n)
    if a >= 1e6 { return "$" + String(format: a >= 1e7 ? "%.0fM" : "%.1fM", n / 1e6) }
    if a >= 1e3 { return "$\(Int((n / 1e3).rounded()))K" }
    return "$\(Int(n.rounded()))"
}

private let sliceColors: [Color] = [.chartNightBlue, .chartSky, .chartGold, .chartEvergreen, .loss, .allworthAccent]

private func successColor(_ rate: Double, onDark: Bool) -> Color {
    if rate >= 90 { return onDark ? .gainOnDark : .gain }
    if rate >= 70 { return .chartGold }
    return onDark ? .lossOnDark : .loss
}

// MARK: - Dispatcher

struct ChatToolWidgetView: View {
    let widget: ToolWidget
    var body: some View {
        switch widget {
        case .goals(let r): GoalFundingCardView(result: r)
        case .projection(let r): ProjectionCardView(result: r)
        case .rebalance(let r): RebalanceCardView(result: r)
        }
    }
}

// MARK: - Catmull-Rom smoothing (matches the RN charts)

private func appendSmooth(_ path: inout Path, _ pts: [CGPoint]) {
    guard pts.count > 1 else { return }
    for i in 0..<(pts.count - 1) {
        let p0 = pts[max(0, i - 1)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[min(pts.count - 1, i + 2)]
        let c1 = CGPoint(x: p1.x + (p2.x - p0.x) / 6, y: p1.y + (p2.y - p0.y) / 6)
        let c2 = CGPoint(x: p2.x - (p3.x - p1.x) / 6, y: p2.y - (p3.y - p1.y) / 6)
        path.addCurve(to: p2, control1: c1, control2: c2)
    }
}
private func smoothPath(_ pts: [CGPoint]) -> Path {
    var p = Path()
    guard let first = pts.first else { return p }
    p.move(to: first); appendSmooth(&p, pts); return p
}

// MARK: - Monte-Carlo fan chart

private struct FanChart: View {
    let snapshots: [ProjectionResult.Snap]
    let height: CGFloat
    let onDark: Bool
    var interactive = false
    @State private var sel: Int? = nil

    var body: some View {
        GeometryReader { geo in chart(width: geo.size.width) }
            .frame(height: height)
    }

    private func chart(width w: CGFloat) -> some View {
            let padL: CGFloat = 44, padR: CGFloat = 12, padT: CGFloat = 8, padB: CGFloat = 22
            let pw = w - padL - padR, ph = height - padT - padB
            let yMax = max((snapshots.map { $0.p75 }.max() ?? 1) * 1.4, 1)
            let last = snapshots.count - 1
            func x(_ i: Int) -> CGFloat { padL + (last == 0 ? 0 : CGFloat(i) / CGFloat(last)) * pw }
            func y(_ v: Double) -> CGFloat { max(padT, min(padT + ph, padT + ph - CGFloat(v / yMax) * ph)) }
            func pts(_ key: KeyPath<ProjectionResult.Snap, Double>) -> [CGPoint] {
                snapshots.enumerated().map { CGPoint(x: x($0.offset), y: y($0.element[keyPath: key])) }
            }
            func band(_ up: KeyPath<ProjectionResult.Snap, Double>, _ low: KeyPath<ProjectionResult.Snap, Double>) -> Path {
                var p = smoothPath(pts(up))
                let lowR = Array(pts(low).reversed())
                if let f = lowR.first { p.addLine(to: f); appendSmooth(&p, lowR) }
                p.closeSubpath(); return p
            }
            let tone: Color = onDark ? Color(hex: 0x9FC3E8) : .allworthAccent
            let lineC: Color = onDark ? .white : .allworthNavy
            let axisC: Color = onDark ? .white.opacity(0.5) : .inkTertiary
            let grid = [0.0, yMax / 2, yMax]
            let xIdx = [0, last / 2, last]
            let s = sel.flatMap { $0 <= last ? snapshots[$0] : nil }

            let canvasView = Canvas { ctx, _ in
                    // baseline + gridlines
                    for v in grid {
                        var g = Path(); g.move(to: CGPoint(x: padL, y: y(v))); g.addLine(to: CGPoint(x: w - padR, y: y(v)))
                        ctx.stroke(g, with: .color(lineC.opacity(v == 0 ? 0.3 : (onDark ? 0.08 : 0.12))),
                                   style: StrokeStyle(lineWidth: 1, dash: v == 0 ? [2, 5] : []))
                    }
                    // bands (outer p5–p95, inner p25–p75)
                    ctx.fill(band(\.p95, \.p5), with: .linearGradient(
                        Gradient(colors: [tone.opacity(onDark ? 0.30 : 0.20), tone.opacity(onDark ? 0.08 : 0.05)]),
                        startPoint: CGPoint(x: 0, y: padT), endPoint: CGPoint(x: 0, y: padT + ph)))
                    ctx.fill(band(\.p75, \.p25), with: .linearGradient(
                        Gradient(colors: [tone.opacity(onDark ? 0.55 : 0.38), tone.opacity(onDark ? 0.24 : 0.16)]),
                        startPoint: CGPoint(x: 0, y: padT), endPoint: CGPoint(x: 0, y: padT + ph)))
                    // median (halo + line)
                    let med = smoothPath(pts(\.median))
                    ctx.stroke(med, with: .color(lineC.opacity(onDark ? 0.22 : 0.12)), style: StrokeStyle(lineWidth: 6, lineCap: .round, lineJoin: .round))
                    ctx.stroke(med, with: .color(lineC), style: StrokeStyle(lineWidth: 2.5, lineCap: .round, lineJoin: .round))
                    // end dot / scrub marker
                    if let s, let i = sel {
                        var v = Path(); v.move(to: CGPoint(x: x(i), y: padT)); v.addLine(to: CGPoint(x: x(i), y: padT + ph))
                        ctx.stroke(v, with: .color(lineC.opacity(0.4)), lineWidth: 1)
                        ctx.fill(Path(ellipseIn: CGRect(x: x(i) - 5, y: y(s.median) - 5, width: 10, height: 10)), with: .color(lineC))
                    } else {
                        ctx.fill(Path(ellipseIn: CGRect(x: x(last) - 3.5, y: y(snapshots[last].median) - 3.5, width: 7, height: 7)), with: .color(lineC))
                    }
                    // y axis ($) + x axis (ages)
                    for v in grid {
                        ctx.draw(Text(usdCompact(v)).font(.system(size: interactive ? 10 : 9)).foregroundColor(axisC),
                                 at: CGPoint(x: padL - 6, y: y(v)), anchor: .trailing)
                    }
                    for idx in xIdx {
                        ctx.draw(Text(interactive ? "Age \(snapshots[idx].age)" : "\(snapshots[idx].age)")
                            .font(.system(size: interactive ? 10 : 9)).foregroundColor(axisC),
                                 at: CGPoint(x: x(idx), y: height - 6), anchor: .center)
                    }
                }

            return ZStack {
                if interactive {
                    canvasView.gesture(DragGesture(minimumDistance: 4).onChanged { g in
                        guard pw > 0 else { return }
                        let i = Int(((g.location.x - padL) / pw * CGFloat(last)).rounded())
                        sel = max(0, min(last, i))
                    }.onEnded { _ in sel = nil })
                } else {
                    canvasView
                }
                if let s, let i = sel {
                    ScrubTip(age: s.age, median: s.median, p25: s.p25, p75: s.p75)
                        .position(x: min(max(x(i), 72), w - 72), y: 30)
                }
            }
    }
}

private struct ScrubTip: View {
    let age: Int; let median: Double; let p25: Double; let p75: Double
    var body: some View {
        VStack(alignment: .leading, spacing: 1) {
            Text("Age \(age)").font(BrandFont.sansBold(11)).foregroundStyle(.white.opacity(0.6))
            Text("\(usdCompact(median)) median").font(BrandFont.sansBold(16)).foregroundStyle(.white).monospacedDigit()
            Text("likely \(usdCompact(p25))–\(usdCompact(p75))").font(BrandFont.sans(11.5)).foregroundStyle(.white.opacity(0.65)).monospacedDigit()
        }
        .padding(.vertical, 8).padding(.horizontal, 10)
        .frame(width: 144, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 10).fill(Color(hex: 0x071C30).opacity(0.94))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(.white.opacity(0.16), lineWidth: 1)))
    }
}

// MARK: - Projection card + detail

private struct ProjectionCardView: View {
    let result: ProjectionResult
    @State private var open = false
    var body: some View {
        let rate = result.successRate.rounded()
        Button { open = true } label: {
            VStack(alignment: .leading, spacing: 10) {
                WidgetHeader(icon: "chart.xyaxis.line", label: "Retirement projection", expand: true)
                Text("\(Int(rate))% on track").font(BrandFont.displayMedium(26)).foregroundStyle(successColor(rate, onDark: false)).monospacedDigit()
                FanChart(snapshots: result.pathSnapshots, height: 150, onDark: false)
                Text("\(result.simulations ?? 500) simulations\(result.assumptions?.endAge.map { " · to age \($0)" } ?? "")")
                    .font(BrandFont.sans(12.5)).foregroundStyle(Color.inkTertiary)
            }
            .padding(14).frame(maxWidth: .infinity, alignment: .leading).card()
        }
        .buttonStyle(.plain)
        .fullScreenCover(isPresented: $open) { ProjectionDetailView(result: result) { open = false } }
    }
}

private struct ProjectionDetailView: View {
    let result: ProjectionResult
    let onClose: () -> Void
    var body: some View {
        let rate = result.successRate.rounded()
        let a = result.assumptions
        let facts: [(String, String)] = [
            ("Starting portfolio", a?.startingPortfolio.map { usd(Int($0)) } ?? "—"),
            ("Annual draw", a?.annualDraw.map { usd(Int($0)) } ?? "—"),
            ("Annual spending", a?.annualSpending.map { usd(Int($0)) } ?? "—"),
            ("Equity allocation", a?.equityAllocation.map { "\(Int(($0 * 100).rounded()))%" } ?? "—"),
        ]
        WidgetDetailScaffold(title: "Retirement projection", onClose: onClose) {
            VStack(alignment: .leading, spacing: 6) {
                Text("\(Int(rate))%").font(BrandFont.displayMedium(56)).foregroundStyle(successColor(rate, onDark: true)).monospacedDigit()
                Text("chance your money lasts\(a?.endAge.map { " to age \($0)" } ?? ""), across \(result.simulations ?? 500) simulated markets")
                    .font(BrandFont.sans(16)).foregroundStyle(.white.opacity(0.78)).lineSpacing(4)
            }
            VStack(alignment: .leading, spacing: 12) {
                FanChart(snapshots: result.pathSnapshots, height: 240, onDark: true, interactive: true)
                HStack(spacing: 16) {
                    LegendSwatch(color: Color(hex: 0x9FC3E8).opacity(0.55), label: "Likely range (25–75%)")
                    LegendSwatch(color: Color(hex: 0x9FC3E8).opacity(0.30), label: "Full range (5–95%)")
                    Spacer()
                    Text("drag to explore").font(BrandFont.sansItalic(11)).foregroundStyle(.white.opacity(0.4))
                }
            }
            .padding(16).background(RoundedRectangle(cornerRadius: 16).fill(.white.opacity(0.06)).overlay(RoundedRectangle(cornerRadius: 16).stroke(.white.opacity(0.1), lineWidth: 1)))
            if let interp = result.interpretation {
                Text(interp).font(BrandFont.sans(16)).foregroundStyle(.white).lineSpacing(6)
            }
            FactGrid(facts: facts)
        }
    }
}

// MARK: - Rebalance card + detail

private struct RebalanceCardView: View {
    let result: RebalanceResult
    @State private var open = false
    var body: some View {
        let n = result.trades.count
        let tax = result.estimated_tax?.total ?? 0
        Button { open = true } label: {
            VStack(alignment: .leading, spacing: 10) {
                WidgetHeader(icon: "arrow.left.arrow.right", label: "Rebalance plan", expand: true)
                Text("\(n) \(n == 1 ? "trade" : "trades")").font(BrandFont.displayMedium(26)).foregroundStyle(Color.allworthNavy).monospacedDigit()
                AllocationShift(result: result, onDark: false, detailed: false)
                Text("To your 60/40 target · ≈ \(usd(Int(tax))) est. tax").font(BrandFont.sans(12.5)).foregroundStyle(Color.inkTertiary)
            }
            .padding(14).frame(maxWidth: .infinity, alignment: .leading).card()
        }
        .buttonStyle(.plain)
        .fullScreenCover(isPresented: $open) { RebalanceDetailView(result: result) { open = false } }
    }
}

private struct RebalanceDetailView: View {
    let result: RebalanceResult
    let onClose: () -> Void
    var body: some View {
        let trades = result.trades.filter { abs($0.amount) > 1 }.sorted { abs($0.amount) > abs($1.amount) }
        let shown = Array(trades.prefix(8))
        let more = trades.count - shown.count
        let tax = result.estimated_tax?.total ?? 0
        WidgetDetailScaffold(title: "Rebalance plan", onClose: onClose) {
            VStack(alignment: .leading, spacing: 6) {
                Text("\(trades.count)").font(BrandFont.displayMedium(56)).foregroundStyle(.white).monospacedDigit()
                Text("tax-aware trades to move from your current mix to the Core-Satellite 60/40 target")
                    .font(BrandFont.sans(16)).foregroundStyle(.white.opacity(0.78)).lineSpacing(4)
            }
            VStack(alignment: .leading, spacing: 14) {
                Text("ALLOCATION: NOW → TARGET").font(BrandFont.sansBold(12)).tracking(0.8).foregroundStyle(.white.opacity(0.6))
                AllocationShift(result: result, onDark: true, detailed: true)
            }
            .padding(16).background(RoundedRectangle(cornerRadius: 16).fill(.white.opacity(0.06)).overlay(RoundedRectangle(cornerRadius: 16).stroke(.white.opacity(0.1), lineWidth: 1)))
            VStack(alignment: .leading, spacing: 0) {
                Text("LARGEST TRADES").font(BrandFont.sansBold(12)).tracking(0.8).foregroundStyle(.white.opacity(0.6)).padding(.bottom, 4)
                ForEach(Array(shown.enumerated()), id: \.offset) { i, t in
                    HStack(spacing: 12) {
                        Text(t.action).font(BrandFont.sansBold(11)).foregroundStyle(Color.allworthNavy)
                            .frame(width: 46).padding(.vertical, 3)
                            .background(Capsule().fill(t.action == "SELL" ? Color.lossOnDark : Color.gainOnDark))
                        Text(t.ticker).font(BrandFont.sansBold(16)).foregroundStyle(.white).frame(maxWidth: .infinity, alignment: .leading)
                        Text(usd(Int(abs(t.amount)))).font(BrandFont.sans(15)).foregroundStyle(.white.opacity(0.85)).monospacedDigit()
                    }
                    .padding(.vertical, 11)
                    .overlay(alignment: .top) { if i > 0 { Rectangle().fill(.white.opacity(0.12)).frame(height: 0.5) } }
                }
                if more > 0 { Text("+ \(more) smaller trades").font(BrandFont.sans(13)).foregroundStyle(.white.opacity(0.5)).padding(.top, 10) }
            }
            FactGrid(facts: [("Est. tax cost", usd(Int(tax))), ("Portfolio value", usd(Int(result.total_portfolio_value ?? 0)))])
        }
    }
}

// The Now → Target allocation shift, colours aligned across the two bars.
private struct AllocationShift: View {
    let result: RebalanceResult
    let onDark: Bool
    var detailed = false

    private var target: [String: Double] { result.target_allocation }
    private var current: [String: Double] { deriveCurrent() }

    private func deriveCurrent() -> [String: Double] {
        let total = result.total_portfolio_value ?? 1
        let post = result.post_trade_allocation ?? [:]
        var net: [String: Double] = [:]
        for t in result.trades { net[t.ticker, default: 0] += (t.action == "BUY" ? t.amount : -t.amount) }
        let tickers = Set(post.keys).union(target.keys).union(net.keys)
        var cur: [String: Double] = [:]; var sum = 0.0
        for tk in tickers {
            let w = max(0, (post[tk] ?? 0) * total - (net[tk] ?? 0)) / total
            cur[tk] = w; sum += w
        }
        return abs(sum - 1) > 0.3 ? target : cur
    }
    private func colorMap() -> [String: Color] {
        let all = Array(Set(target.keys).union(current.keys))
            .sorted { (target[$0] ?? 0, current[$0] ?? 0) > (target[$1] ?? 0, current[$1] ?? 0) }
        var m: [String: Color] = [:]
        for (i, tk) in all.enumerated() { m[tk] = sliceColors[i % sliceColors.count] }
        return m
    }

    var body: some View {
        let cm = colorMap()
        let labelC: Color = onDark ? .white.opacity(0.55) : .inkTertiary
        let top = target.filter { $0.value > 0.002 }.sorted { $0.value > $1.value }.prefix(5)
        VStack(alignment: .leading, spacing: detailed ? 14 : 11) {
            mix("NOW", current, cm, labelC)
            mix("TARGET", target, cm, labelC)
            if detailed {
                VStack(spacing: 10) {
                    ForEach(Array(top), id: \.key) { tk, w in
                        HStack(spacing: 10) {
                            Circle().fill(cm[tk] ?? .chartLightGray).frame(width: 9, height: 9)
                            Text(tk).font(BrandFont.sansBold(15)).foregroundStyle(onDark ? .white : .inkPrimary).frame(maxWidth: .infinity, alignment: .leading)
                            Text("\(Int(((current[tk] ?? 0) * 100).rounded()))% → \(Int((w * 100).rounded()))%")
                                .font(BrandFont.sans(14)).foregroundStyle(onDark ? .white.opacity(0.85) : .inkSecondary).monospacedDigit()
                        }
                    }
                }
                .padding(.top, 2)
            }
        }
    }
    private func mix(_ label: String, _ alloc: [String: Double], _ cm: [String: Color], _ labelC: Color) -> some View {
        let entries = alloc.filter { $0.value > 0.002 }.sorted { $0.value > $1.value }
        return VStack(alignment: .leading, spacing: 5) {
            Text(label).font(BrandFont.sansBold(11)).tracking(0.6).foregroundStyle(labelC)
            GeometryReader { geo in
                HStack(spacing: 0) {
                    ForEach(entries, id: \.key) { tk, w in
                        Rectangle().fill(cm[tk] ?? .chartLightGray).frame(width: geo.size.width * w)
                    }
                }
            }
            .frame(height: 14).clipShape(Capsule())
        }
    }
}

// MARK: - Goal funding card (reuses the live GoalDials)

private struct GoalFundingCardView: View {
    let result: GoalFundingResult
    @State private var openId: String?
    var body: some View {
        let rate = result.assumedGrowthRate ?? 0.06
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                Image(systemName: "flag").font(.system(size: 13)).foregroundStyle(Color.allworthAccent)
                Text("Your goals").font(BrandFont.sansBold(13)).foregroundStyle(Color.inkSecondary)
                Spacer()
                Text(result.summary).font(BrandFont.sans(12)).foregroundStyle(Color.inkTertiary)
            }
            ForEach(Array(result.goals.enumerated()), id: \.element.id) { i, g in
                if i > 0 { Divider().background(Color.hairline).padding(.vertical, 4) }
                goalRow(g, rate: rate)
            }
        }
        .padding(14).frame(maxWidth: .infinity, alignment: .leading).card()
    }

    private func onTrack(_ g: APIGoal) -> Bool { g.onTrack ?? (g.status == "on_track") }

    @ViewBuilder private func goalRow(_ g: APIGoal, rate: Double) -> some View {
        if g.isIncome {
            VStack(alignment: .leading, spacing: 3) {
                HStack {
                    Text(g.label).font(BrandFont.sansBold(14)).foregroundStyle(Color.inkPrimary)
                    Spacer()
                    Text(onTrack(g) ? "On track" : "At risk").font(BrandFont.sansBold(12)).foregroundStyle(onTrack(g) ? Color.gain : Color.attention)
                }
                if let d = g.detail { Text(d).font(BrandFont.sans(12)).foregroundStyle(Color.inkSecondary) }
            }
        } else {
            VStack(alignment: .leading, spacing: 5) {
                Button { openId = openId == g.id ? nil : g.id } label: {
                    VStack(alignment: .leading, spacing: 5) {
                        HStack(spacing: 6) {
                            Text(g.label).font(BrandFont.sansBold(14)).foregroundStyle(Color.inkPrimary).frame(maxWidth: .infinity, alignment: .leading)
                            Text(onTrack(g) ? "On track" : "Needs attention").font(BrandFont.sansBold(12)).foregroundStyle(onTrack(g) ? Color.gain : Color.attention)
                            Image(systemName: openId == g.id ? "chevron.up" : "chevron.down").font(.system(size: 12)).foregroundStyle(Color.inkTertiary)
                        }
                        GeometryReader { geo in
                            ZStack(alignment: .leading) {
                                Capsule().fill(Color.inkFaint)
                                Capsule().fill(onTrack(g) ? Color.chartEvergreen : Color.loss)
                                    .frame(width: geo.size.width * min(1, Double(g.fundedPct ?? 0) / 100))
                            }
                        }
                        .frame(height: 6)
                        Text(fundedText(g)).font(BrandFont.sans(12)).foregroundStyle(Color.inkSecondary).monospacedDigit()
                    }
                }
                .buttonStyle(.plain)
                if openId == g.id {
                    GoalDials(goal: g, rate: rate)
                        .padding(.top, 10)
                        .overlay(alignment: .top) { Rectangle().fill(Color.hairline).frame(height: 0.5) }
                }
            }
        }
    }
    private func fundedText(_ g: APIGoal) -> String {
        let base = "\(usd(g.currentFunded ?? 0)) of \(usd(g.target ?? 0))"
        if let m = g.committedMonthly { return base + " · your plan: \(usd(Int(m)))/mo" }
        if onTrack(g) { return base }
        return base + " · ~\(usd(g.monthlyContributionToClose ?? 0))/mo closes the gap"
    }
}

// MARK: - Shared chrome

private struct WidgetHeader: View {
    let icon: String; let label: String; var expand = false
    var body: some View {
        HStack(spacing: 8) {
            ZStack {
                RoundedRectangle(cornerRadius: 8).fill(Color.allworthAccent.opacity(0.12)).frame(width: 26, height: 26)
                Image(systemName: icon).font(.system(size: 14)).foregroundStyle(Color.allworthAccent)
            }
            Text(label).font(BrandFont.sansBold(13)).foregroundStyle(Color.inkSecondary).frame(maxWidth: .infinity, alignment: .leading)
            if expand { Image(systemName: "arrow.up.left.and.arrow.down.right").font(.system(size: 13)).foregroundStyle(Color.inkTertiary) }
        }
    }
}

private struct LegendSwatch: View {
    let color: Color; let label: String
    var body: some View {
        HStack(spacing: 6) {
            RoundedRectangle(cornerRadius: 3).fill(color).frame(width: 12, height: 12)
            Text(label).font(BrandFont.sans(12)).foregroundStyle(.white.opacity(0.7))
        }
    }
}

private struct FactGrid: View {
    let facts: [(String, String)]
    let cols = [GridItem(.flexible(), spacing: 12), GridItem(.flexible(), spacing: 12)]
    var body: some View {
        LazyVGrid(columns: cols, spacing: 12) {
            ForEach(Array(facts.enumerated()), id: \.offset) { _, f in
                VStack(alignment: .leading, spacing: 2) {
                    Text(f.1).font(BrandFont.displayMedium(19)).foregroundStyle(.white).monospacedDigit()
                    Text(f.0).font(BrandFont.sans(12.5)).foregroundStyle(.white.opacity(0.6))
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(14).background(RoundedRectangle(cornerRadius: 12).fill(.white.opacity(0.06)))
            }
        }
    }
}

// Full-screen navy scaffold shared by the projection + rebalance details.
private struct WidgetDetailScaffold<Content: View>: View {
    let title: String
    let onClose: () -> Void
    @ViewBuilder let content: () -> Content
    var body: some View {
        ZStack {
            Color.chartNightBlue.ignoresSafeArea()
            VStack(spacing: 0) {
                HStack {
                    Button(action: onClose) { Image(systemName: "xmark").font(.system(size: 22, weight: .medium)).foregroundStyle(.white) }
                    Spacer()
                    Text(title).font(BrandFont.sansBold(16)).foregroundStyle(.white)
                    Spacer()
                    AllworthMark(color: .white, size: 22)
                }
                .padding(.horizontal, 20).padding(.bottom, 6)
                ScrollView(showsIndicators: false) {
                    VStack(alignment: .leading, spacing: 22) { content() }
                        .padding(20).padding(.bottom, 28)
                }
            }
        }
    }
}
