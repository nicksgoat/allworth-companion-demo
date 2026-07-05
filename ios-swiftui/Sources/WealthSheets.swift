import SwiftUI

// The tapped-in Wealth detail sheets, ported 1:1 from screens/NetWorthDetail,
// NudgeDetailSheet, ClassDetailSheet, PositionDetailSheet.

// MARK: - Net worth detail (full navy modal)

struct NetWorthDetailSheet: View {
    let onClose: () -> Void
    @State private var range = "1Y"

    private let ranges = ["3M", "6M", "1Y"]

    private var slice: [Double] {
        let h = Demo.netWorthHistory
        switch range {
        case "3M": return Array(h.suffix(3))
        case "6M": return Array(h.suffix(6))
        default: return h
        }
    }

    private var deltaText: String {
        if range == "1Y" { return "↑ " + Demo.netWorthChange }
        let s = slice
        guard let first = s.first, let last = s.last, first != 0 else { return "" }
        let diff = Int(last - first)
        let pct = (last - first) / first * 100
        let suffix = range == "3M" ? "past 3 months" : "past 6 months"
        let arrow = diff >= 0 ? "↑" : "↓"
        return String(format: "%@ +%@ (+%.1f%%) %@", arrow, usd(diff), pct, suffix)
    }

    var body: some View {
        VStack(spacing: 18) {
            HStack {
                Button(action: onClose) {
                    Image(systemName: "xmark").font(.system(size: 22, weight: .medium)).foregroundStyle(.white)
                }
                Spacer()
                VStack(spacing: 1) {
                    Text("Net worth").font(BrandFont.sansBold(16)).foregroundStyle(.white)
                    Text("as of today").font(BrandFont.sans(12)).foregroundStyle(.white.opacity(0.6))
                }
                Spacer()
                AllworthMark(color: .white, size: 22)
            }

            VStack(alignment: .leading, spacing: 6) {
                Text(usd(Demo.netWorth)).font(BrandFont.display(44)).foregroundStyle(.white).monospacedDigit()
                Text(deltaText).font(BrandFont.sansBold(17)).foregroundStyle(Color.gainOnDark).monospacedDigit()
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            SmoothChart(values: slice)
                .frame(maxHeight: .infinity)

            HStack(spacing: 0) {
                ForEach(ranges, id: \.self) { r in
                    let on = r == range
                    Text(r)
                        .font(BrandFont.sansBold(15))
                        .foregroundStyle(on ? .white : .white.opacity(0.55))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                        .background(RoundedRectangle(cornerRadius: 8).fill(.white.opacity(on ? 0.15 : 0)))
                        .contentShape(Rectangle())
                        .onTapGesture { range = r }
                }
            }

            Text("Educational information, not investment advice. Allworth Financial demo — synthetic data.")
                .font(BrandFont.sans(11)).foregroundStyle(.white.opacity(0.5))
                .multilineTextAlignment(.center).lineSpacing(3)
        }
        .padding(.horizontal, 20)
        .padding(.top, 6)
        .padding(.bottom, 16)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.nightBlue.ignoresSafeArea())
    }
}

// MARK: - Nudge detail (severity-tinted hero)

struct NudgeDetailSheet: View {
    let nudge: Demo.NudgeInfo
    let onClose: () -> Void

    private var sevColor: Color { nudge.severity.color }

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                hero
                VStack(spacing: 20) {
                    Text(nudge.body)
                        .font(BrandFont.sans(17)).foregroundStyle(Color.inkPrimary).lineSpacing(7)
                        .frame(maxWidth: .infinity, alignment: .leading)

                    if nudge.kind == .spending { SpendingBars() }
                    if nudge.kind == .concentration, let pct = nudge.concentrationPct {
                        ConcentrationBar(pct: pct, color: sevColor, headline: nudge.headline)
                    }

                    HStack(spacing: 8) {
                        Image(systemName: "bubble.left.and.bubble.right").font(.system(size: 18)).foregroundStyle(.white)
                        Text(nudge.cta).font(BrandFont.sansBold(17)).foregroundStyle(.white)
                    }
                    .frame(maxWidth: .infinity).padding(.vertical, 15)
                    .background(RoundedRectangle(cornerRadius: 12).fill(Color.allworthAccent))

                    AdvisorHandoffCard()
                    DisclaimerFooter()
                }
                .padding(20)
            }
        }
        .background(Color.surfacePrimary.ignoresSafeArea())
    }

    private var hero: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                ZStack {
                    RoundedRectangle(cornerRadius: 14, style: .continuous).fill(sevColor).frame(width: 42, height: 42)
                    Image(systemName: nudge.icon).font(.system(size: 20)).foregroundStyle(.white)
                }
                Spacer()
                Button(action: onClose) {
                    ZStack {
                        Circle().fill(.white.opacity(0.7)).frame(width: 32, height: 32)
                        Image(systemName: "xmark").font(.system(size: 18, weight: .medium)).foregroundStyle(Color.inkSecondary)
                    }
                }
                .buttonStyle(.plain)
            }
            Text(nudge.severity.label)
                .font(BrandFont.sansBold(12)).tracking(0.3).foregroundStyle(sevColor)
                .padding(.horizontal, 10).padding(.vertical, 4)
                .background(Capsule().fill(.white.opacity(0.6)))
            Text(nudge.headline).font(BrandFont.displayMedium(40)).foregroundStyle(sevColor).monospacedDigit()
            Text(nudge.title).font(BrandFont.sans(18)).foregroundStyle(Color.inkPrimary).lineSpacing(6)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 20).padding(.top, 22).padding(.bottom, 22)
        .background(sevColor.opacity(0.10))
        .clipShape(.rect(bottomLeadingRadius: 24, bottomTrailingRadius: 24))
    }
}

private struct SpendingBars: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader("Last \(Demo.spendMonths.count) months vs plan")
            ForEach(Demo.spendMonths) { m in
                let ratio = min(1.0, Double(m.total) / Double(Demo.spendPlan) / 1.4)
                let over = m.total > Demo.spendPlan
                HStack(spacing: 10) {
                    Text(m.month).font(BrandFont.sans(13)).foregroundStyle(Color.inkTertiary).monospacedDigit().frame(width: 30, alignment: .leading)
                    GeometryReader { geo in
                        ZStack(alignment: .leading) {
                            Capsule().fill(Color.inkFaint)
                            Capsule().fill(over ? Color.attention : Color.allworthNavy).frame(width: geo.size.width * ratio)
                        }
                    }
                    .frame(height: 8)
                    Text(usd(m.total)).font(BrandFont.sans(13)).foregroundStyle(Color.inkSecondary).monospacedDigit().frame(width: 64, alignment: .trailing)
                }
            }
            Text("Plan: \(usd(Demo.spendPlan))/mo · Recent average: \(usd(Demo.spendAvg3mo))/mo")
                .font(BrandFont.sans(13)).foregroundStyle(Color.inkTertiary)
        }
    }
}

private struct ConcentrationBar: View {
    let pct: Int
    let color: Color
    let headline: String
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader("Share of the account")
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(Color.inkFaint)
                    Capsule().fill(color).frame(width: geo.size.width * CGFloat(min(100, pct)) / 100)
                }
            }
            .frame(height: 14)
            HStack {
                Text(headline).font(BrandFont.sansBold(15)).foregroundStyle(color).monospacedDigit()
                Spacer()
                Text("\(max(0, 100 - pct))% everything else").font(BrandFont.sans(14)).foregroundStyle(Color.inkTertiary)
            }
        }
    }
}

// MARK: - Asset class detail

struct ClassDetailSheet: View {
    let key: String
    let onClose: () -> Void

    private var meta: (label: String, color: Color, blurb: String) {
        Demo.classMeta[key] ?? ("", .allworthNavy, "")
    }
    private var holdings: [Demo.Position] { Demo.classHoldings(key) }
    private var classTotal: Int { Demo.classTotal(key) }
    private var classPct: Int { Demo.investedTotal == 0 ? 0 : Int((Double(classTotal) / Double(Demo.investedTotal) * 100).rounded()) }
    private var growth: Bool { key == "us_equity" || key == "intl_equity" }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                SheetHeaderView(title: "Your allocation", onClose: onClose)

                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 10) {
                        Circle().fill(meta.color).frame(width: 12, height: 12)
                        Text(meta.label).font(BrandFont.display(28)).foregroundStyle(Color.inkPrimary)
                    }
                    Text(usd(classTotal)).font(BrandFont.displayMedium(40)).foregroundStyle(Color.inkPrimary).monospacedDigit()
                    Text("\(classPct)% of your invested portfolio").font(BrandFont.sans(14)).foregroundStyle(Color.inkTertiary)
                }

                Text(growth
                     ? "Part of the growth side of your 60/40 plan — built for long-term appreciation."
                     : "Part of the income & stability side of your 60/40 plan — there to steady the portfolio.")
                    .font(BrandFont.sans(15)).foregroundStyle(Color.inkSecondary).lineSpacing(7)

                VStack(alignment: .leading, spacing: 4) {
                    SectionHeader("Holdings in \(meta.label.lowercased())")
                    ForEach(Array(holdings.enumerated()), id: \.element.id) { i, p in
                        if i > 0 { Hairline() }
                        HStack(spacing: 12) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(p.symbol).font(BrandFont.sans(17)).foregroundStyle(Color.inkPrimary)
                                Text(Demo.accountLabel(p.accountId)).font(BrandFont.sans(13)).foregroundStyle(Color.inkTertiary).lineLimit(1)
                            }
                            Spacer()
                            VStack(alignment: .trailing, spacing: 2) {
                                Text(usd(p.value)).font(BrandFont.sansBold(17)).foregroundStyle(Color.inkPrimary).monospacedDigit()
                                Text("\(classTotal == 0 ? 0 : Int((Double(p.value) / Double(classTotal) * 100).rounded()))% of class")
                                    .font(BrandFont.sans(13)).foregroundStyle(Color.inkTertiary).monospacedDigit()
                            }
                        }
                        .padding(.vertical, 12)
                    }
                }

                sheetCTA("Ask how this fits my plan")
                DisclaimerFooter()
            }
            .padding(20)
        }
        .background(Color.surfacePrimary.ignoresSafeArea())
    }
}

// MARK: - Position detail

struct PositionDetailSheet: View {
    let position: Demo.Position
    let onClose: () -> Void
    @State private var range = "1Y"

    private var account: Demo.Account? { Demo.account(position.accountId) }
    private var hasTax: Bool { position.costBasis != nil }
    private var basis: Int { position.costBasis ?? position.value }
    private var gain: Int { position.value - basis }
    private var gainPct: Int { basis == 0 ? 0 : Int((Double(gain) / Double(basis) * 100).rounded()) }
    private var hasShort: Bool { abs(position.shortTermUnrealizedGain ?? 0) > 0 }

    private var series: [Double] {
        let full = syntheticSeries(seed: position.symbol + position.accountId, end: Double(position.value), count: 12)
        switch range { case "3M": return Array(full.suffix(4)); case "6M": return Array(full.suffix(7)); default: return full }
    }
    private var perf: (diff: Int, pct: Double) {
        let s = series
        guard let f = s.first, let l = s.last, f != 0 else { return (0, 0) }
        return (Int(l - f), (l - f) / f * 100)
    }
    private var rangeSuffix: String { range == "3M" ? "past 3 months" : range == "6M" ? "past 6 months" : "past year" }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                SheetHeaderView(title: account.map { "\($0.name) · \($0.institution)" } ?? "Holding", onClose: onClose)

                VStack(alignment: .leading, spacing: 4) {
                    Text(position.symbol).font(BrandFont.display(34)).foregroundStyle(Color.inkPrimary)
                    Text(position.name).font(BrandFont.sans(15)).foregroundStyle(Color.inkSecondary)
                }

                VStack(alignment: .leading, spacing: 2) {
                    Text(usd(position.value)).font(BrandFont.displayMedium(40)).foregroundStyle(Color.inkPrimary).monospacedDigit()
                    Text("\(shares) shares · \(usdExact(position.price)) each").font(BrandFont.sans(14)).foregroundStyle(Color.inkTertiary).monospacedDigit()
                }

                VStack(alignment: .leading, spacing: 12) {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text("\(perf.diff >= 0 ? "+" : "")\(usd(perf.diff)) (\(perf.diff >= 0 ? "+" : "−")\(String(format: "%.1f", abs(perf.pct)))%) \(rangeSuffix)")
                            .font(BrandFont.sansBold(15)).foregroundStyle(perf.diff >= 0 ? Color.gain : Color.loss).monospacedDigit()
                        Text("illustrative").font(BrandFont.sansItalic(11)).foregroundStyle(Color.inkTertiary)
                    }
                    SmoothChart(values: series, lineColor: perf.diff >= 0 ? .gain : .loss, lineWidth: 2,
                                fillTop: (perf.diff >= 0 ? Color.gain : Color.loss).opacity(0.14), fillBottom: .clear,
                                showBaseline: false, showEndDot: true, haloOpacity: 0)
                        .frame(height: 90)
                    RangeChipsRow(selected: $range)
                }

                if hasTax {
                    VStack(alignment: .leading, spacing: 10) {
                        SectionHeader("Cost basis & gains")
                        if let avg = position.averageCostBasis {
                            basisRow("Average cost basis", "\(usdExact(avg)) / share"); Hairline()
                        }
                        basisRow("Cost basis", usd(basis)); Hairline()
                        basisRow("Market value", usd(position.value)); Hairline()
                        basisRow("Unrealized gain", "\(gain >= 0 ? "+" : "")\(usd(gain)) (\(gainPct)%)", color: gain >= 0 ? .gain : .loss)
                        if let lt = position.longTermUnrealizedGain, abs(lt) > 0 {
                            Hairline(); basisRow("Long-term unrealized gain", "\(lt >= 0 ? "+" : "")\(usd(lt))", color: lt >= 0 ? .gain : .loss)
                        }
                        if hasShort, let st = position.shortTermUnrealizedGain {
                            Hairline(); basisRow("Short-term unrealized gain", "\(st >= 0 ? "+" : "")\(usd(st))", color: st >= 0 ? .gain : .loss)
                        }
                    }
                    .padding(16).card()
                } else {
                    Text("Held in a tax-advantaged account — selling here has no capital-gains impact.")
                        .font(BrandFont.sans(14)).foregroundStyle(Color.inkSecondary).lineSpacing(6)
                        .frame(maxWidth: .infinity, alignment: .leading).padding(16).card()
                }

                if hasShort {
                    Text("Some of this position appears short-term on an aggregate basis, which can change the tax estimate before selling.")
                        .font(BrandFont.sans(13)).foregroundStyle(Color.attention).lineSpacing(6)
                }

                sheetCTA(hasTax ? "Ask about the tax impact" : "Ask how this fits my plan")
                AdvisorHandoffCard()

                Text("Chart and gains are illustrative, generated for this demo — not market data. Past performance doesn't guarantee future results.")
                    .font(BrandFont.sans(11)).foregroundStyle(Color.inkTertiary).multilineTextAlignment(.center).lineSpacing(4)
                    .frame(maxWidth: .infinity)
                DisclaimerFooter()
            }
            .padding(20)
        }
        .background(Color.surfacePrimary.ignoresSafeArea())
    }

    private var shares: String {
        let f = NumberFormatter(); f.numberStyle = .decimal
        return f.string(from: NSNumber(value: position.qty)) ?? "\(Int(position.qty))"
    }

    private func basisRow(_ label: String, _ value: String, color: Color? = nil) -> some View {
        HStack {
            Text(label).font(BrandFont.sans(15)).foregroundStyle(Color.inkSecondary)
            Spacer()
            Text(value).font(BrandFont.sansBold(15)).foregroundStyle(color ?? Color.inkPrimary).monospacedDigit()
        }
        .padding(.vertical, 4)
    }
}

// MARK: - Shared bits

// "$226.33" — per-share prices need cents (usd() rounds).
func usdExact(_ n: Double) -> String {
    let f = NumberFormatter()
    f.numberStyle = .decimal
    f.minimumFractionDigits = 2
    f.maximumFractionDigits = 2
    return "$" + (f.string(from: NSNumber(value: n)) ?? String(format: "%.2f", n))
}

func sheetCTA(_ title: String) -> some View {
    HStack(spacing: 8) {
        Image(systemName: "bubble.left.and.bubble.right").font(.system(size: 18)).foregroundStyle(.white)
        Text(title).font(BrandFont.sansBold(17)).foregroundStyle(.white)
    }
    .frame(maxWidth: .infinity).padding(.vertical, 14)
    .background(RoundedRectangle(cornerRadius: 12).fill(Color.allworthAccent))
}

struct RangeChipsRow: View {
    @Binding var selected: String
    private let options = ["3M", "6M", "1Y"]
    var body: some View {
        HStack(spacing: 0) {
            ForEach(options, id: \.self) { o in
                let on = o == selected
                Text(o)
                    .font(BrandFont.sansBold(14)).foregroundStyle(on ? Color.inkPrimary : Color.inkTertiary)
                    .frame(maxWidth: .infinity).padding(.vertical, 7)
                    .background(RoundedRectangle(cornerRadius: 8).fill(on ? Color.inkFaint : .clear))
                    .contentShape(Rectangle())
                    .onTapGesture { selected = o }
            }
        }
    }
}
