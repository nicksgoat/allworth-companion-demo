import SwiftUI

// MARK: - Breakdown card (managed / held away / liabilities)

struct BreakdownCard: View {
    let managed: Int
    let heldAway: Int
    let liabilities: Int

    var body: some View {
        VStack(spacing: Space.s3) {
            // Proportion bar — navy (managed) vs cerulean (held away).
            GeometryReader { geo in
                let total = CGFloat(managed + heldAway)
                HStack(spacing: 0) {
                    Rectangle().fill(Color.allworthNavy)
                        .frame(width: geo.size.width * CGFloat(managed) / total)
                    Rectangle().fill(Color.allworthAccent)
                }
            }
            .frame(height: 10)
            .clipShape(Capsule())
            .padding(.bottom, 2)

            row(dot: .allworthNavy, label: "Managed by Allworth", sub: nil, value: managed, negative: false)
            Divider().background(Color.hairline)
            row(dot: .allworthAccent, label: "Held away", sub: "Not yet part of your Allworth plan", value: heldAway, negative: false)
            Divider().background(Color.hairline)
            row(dot: nil, label: "Liabilities", sub: nil, value: -liabilities, negative: true)
        }
        .padding(16)
        .card()
    }

    private func row(dot: Color?, label: String, sub: String?, value: Int, negative: Bool) -> some View {
        HStack(spacing: 10) {
            Circle().fill(dot ?? .clear).frame(width: 8, height: 8)
            VStack(alignment: .leading, spacing: 1) {
                Text(label).font(BrandFont.sans(15)).foregroundStyle(Color.inkPrimary)
                if let sub { Text(sub).font(BrandFont.sans(12)).foregroundStyle(Color.inkTertiary) }
            }
            Spacer()
            Text(usd(value))
                .font(BrandFont.sansBold(15))
                .foregroundStyle(negative ? Color.loss : Color.inkPrimary)
                .monospacedDigit()
        }
        .padding(.vertical, 4)
    }
}

// MARK: - Segmented control (Overview / Holdings)

struct SegmentedControl: View {
    let options: [String]
    @Binding var selected: String

    var body: some View {
        HStack(spacing: 0) {
            ForEach(options, id: \.self) { opt in
                let active = opt == selected
                Text(opt)
                    .font(BrandFont.sansBold(15))
                    .foregroundStyle(active ? Color.inkPrimary : Color.inkSecondary)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 11)
                    .background(
                        active
                            ? AnyView(RoundedRectangle(cornerRadius: 8, style: .continuous)
                                .fill(.white)
                                .shadow(color: Color.nightBlue.opacity(0.06), radius: 3, y: 1))
                            : AnyView(Color.clear)
                    )
                    .contentShape(Rectangle())
                    .onTapGesture { selected = opt }
            }
        }
        .padding(3)
        .background(RoundedRectangle(cornerRadius: 10, style: .continuous).fill(Color.inkFaint))
    }
}

// MARK: - Donut chart (chunky, gapped, brand-secondary segments)

struct DonutChart: View {
    let segments: [(value: Double, color: Color)]
    var size: CGFloat = 196
    var thickness: CGFloat = 22

    var body: some View {
        let total = max(segments.reduce(0) { $0 + $1.value }, 1)
        let gap = 0.006
        ZStack {
            ForEach(Array(segments.enumerated()), id: \.offset) { i, seg in
                let start = segments[0..<i].reduce(0) { $0 + $1.value } / total
                let frac = seg.value / total
                Circle()
                    .trim(from: start + gap, to: start + frac - gap)
                    .stroke(seg.color, style: StrokeStyle(lineWidth: thickness, lineCap: .butt))
                    .rotationEffect(.degrees(-90))
                    .padding(thickness / 2)
            }
        }
        .frame(width: size, height: size)
    }
}

// MARK: - Allocation card (donut + legend + drift + ask)

struct AllocationCard: View {
    var onSelectClass: (String) -> Void = { _ in }
    var body: some View {
        VStack(spacing: 14) {
            ZStack {
                DonutChart(segments: Demo.allocation.map { (Double($0.value), $0.color) })
                VStack(spacing: -2) {
                    Text("\(Demo.equityPct)%").font(BrandFont.displayMedium(38)).foregroundStyle(Color.allworthNavy).monospacedDigit()
                    Text("in stocks").font(BrandFont.sans(14)).foregroundStyle(Color.inkTertiary)
                }
            }
            .padding(.vertical, 4)

            VStack(spacing: 0) {
                ForEach(Array(Demo.allocation.enumerated()), id: \.element.id) { i, c in
                    if i > 0 { Divider().background(Color.hairline) }
                    HStack(spacing: 12) {
                        RoundedRectangle(cornerRadius: 3).fill(c.color).frame(width: 5, height: 34)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(c.label).font(BrandFont.sansBold(16)).foregroundStyle(Color.inkPrimary).lineLimit(1)
                            Text(usd(c.value)).font(BrandFont.sans(13)).foregroundStyle(Color.inkTertiary).monospacedDigit()
                        }
                        Spacer()
                        Text("\(c.pct)%").font(BrandFont.sansBold(16)).foregroundStyle(Color.inkPrimary).monospacedDigit()
                        Image(systemName: "chevron.right").font(.system(size: 14, weight: .semibold)).foregroundStyle(Color.inkTertiary)
                    }
                    .padding(.vertical, 12)
                    .contentShape(Rectangle())
                    .onTapGesture { onSelectClass(c.key) }
                }
            }

            Text(Demo.driftText)
                .font(BrandFont.sans(14)).foregroundStyle(Color.attention).lineSpacing(4)
                .frame(maxWidth: .infinity, alignment: .leading)

            Text("Ask Allworth AI about rebalancing")
                .font(BrandFont.sansBold(15)).foregroundStyle(Color.allworthAccent)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
                .background(RoundedRectangle(cornerRadius: 12).fill(Color.allworthAccent.opacity(0.12)))
        }
        .padding(16)
        .card()
    }
}

// MARK: - Advisor handoff ("Bring this to Nicole")

struct AdvisorHandoffCard: View {
    var body: some View {
        VStack(spacing: 14) {
            HStack(spacing: 12) {
                ZStack {
                    Circle().fill(Color.allworthNavy).frame(width: 44, height: 44)
                    Text(Demo.advisorInitials).font(BrandFont.sansBold(15)).tracking(0.5).foregroundStyle(.white)
                }
                VStack(alignment: .leading, spacing: 1) {
                    Text("Bring this to \(Demo.advisorFirst)").font(BrandFont.sansBold(17)).foregroundStyle(Color.inkPrimary)
                    Text(Demo.advisorTitle).font(BrandFont.sans(13)).foregroundStyle(Color.inkSecondary)
                }
                Spacer(minLength: 0)
            }
            HStack(spacing: 10) {
                Text("Message")
                    .font(BrandFont.sansBold(15)).foregroundStyle(.white)
                    .frame(maxWidth: .infinity).padding(.vertical, 13)
                    .background(RoundedRectangle(cornerRadius: 12).fill(Color.allworthAccent))
                Text("Schedule")
                    .font(BrandFont.sansBold(15)).foregroundStyle(Color.allworthAccent)
                    .frame(maxWidth: .infinity).padding(.vertical, 13)
                    .background(RoundedRectangle(cornerRadius: 12).fill(Color.allworthAccent.opacity(0.12)))
            }
        }
        .padding(16)
        .card()
    }
}

// MARK: - Concentration nudge card

struct NudgeCard: View {
    let nudge: Demo.NudgeInfo
    var onTap: () -> Void = {}

    private var pct: Int { nudge.concentrationPct ?? 0 }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Image(systemName: "chart.pie")
                    .font(.system(size: 17)).foregroundStyle(Color.allworthAccent)
                    .frame(width: 40, height: 40)
                    .background(RoundedRectangle(cornerRadius: Radius.chip).fill(Color.ice))
                Spacer()
                Text("Insight")
                    .font(BrandFont.sansBold(13)).foregroundStyle(Color.allworthAccent)
                    .padding(.horizontal, 12).padding(.vertical, 5)
                    .background(Capsule().fill(Color.allworthAccent.opacity(0.12)))
            }
            VStack(alignment: .leading, spacing: 6) {
                Text("\(pct)% of the account")
                    .font(BrandFont.displayMedium(34)).foregroundStyle(Color.chartSky)
                Text(nudge.title).font(BrandFont.sans(16)).foregroundStyle(Color.inkPrimary)
            }
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(Color.inkFaint)
                    Capsule().fill(Color.chartSky).frame(width: geo.size.width * CGFloat(pct) / 100)
                }
            }
            .frame(height: 8)
            HStack {
                Text("Ask me about my options").font(BrandFont.sansBold(15)).foregroundStyle(Color.allworthAccent)
                Spacer()
                Image(systemName: "arrow.right").font(.system(size: 16, weight: .semibold)).foregroundStyle(Color.allworthAccent)
            }
        }
        .padding(16)
        .card()
        .contentShape(Rectangle())
        .onTapGesture(perform: onTap)
    }
}

// MARK: - Complete-your-picture card

struct CompletePictureCard: View {
    var body: some View {
        VStack(spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: "plus.circle").font(.system(size: 22)).foregroundStyle(Color.allworthAccent)
                VStack(alignment: .leading, spacing: 4) {
                    Text("Complete your picture").font(BrandFont.sansBold(17)).foregroundStyle(Color.inkPrimary)
                    Text("We can see \(usd(Demo.heldAway)) held away. Linking the rest helps \(Demo.advisorFirst) plan around everything you own — taxes, risk, and all.")
                        .font(BrandFont.sans(14)).foregroundStyle(Color.inkSecondary).lineSpacing(3)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            Text("Link an account")
                .font(BrandFont.sansBold(15)).foregroundStyle(.white)
                .frame(maxWidth: .infinity).padding(.vertical, 12)
                .background(RoundedRectangle(cornerRadius: 10).fill(Color.allworthAccent))
        }
        .padding(16)
        .card()
    }
}

// MARK: - Account holdings section (Holdings segment)

// Glance rule: the account header (name, institution, count, total) is always
// visible; the position rows unfold on tap. Cash rows aren't tappable.
struct AccountHoldingsSection: View {
    let account: Demo.Account
    var onSelect: (Demo.Position) -> Void = { _ in }
    @State var expanded: Bool

    private static let funds: Set<String> = ["VTI", "VXUS", "VTEB", "BND", "FXAIX", "FSPSX", "FXNAX", "SPAXX"]

    private var sorted: [Demo.Position] { account.positions.sorted { $0.value > $1.value } }
    private var total: Int { account.positions.reduce(0) { $0 + $1.value } }

    var body: some View {
        VStack(spacing: 0) {
            Button { withAnimation(.easeInOut(duration: 0.2)) { expanded.toggle() } } label: {
                HStack(spacing: 12) {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(account.name).font(BrandFont.sansBold(15)).foregroundStyle(Color.inkPrimary)
                        Text("\(account.institution) · \(sorted.count) holding\(sorted.count == 1 ? "" : "s")")
                            .font(BrandFont.sans(12)).foregroundStyle(Color.inkTertiary)
                    }
                    Spacer()
                    Text(usd(total)).font(BrandFont.sansBold(15)).foregroundStyle(Color.inkSecondary).monospacedDigit()
                    Image(systemName: expanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 13, weight: .semibold)).foregroundStyle(Color.inkTertiary)
                }
                .padding(.vertical, 12)
            }
            .buttonStyle(.plain)

            if expanded {
                ForEach(sorted) { p in
                    Hairline()
                    holdingRow(p)
                }
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 6)
        .card()
    }

    private func isConcentrated(_ p: Demo.Position) -> Bool {
        if p.assetClass == "cash" || p.symbol == "CASH" { return false }
        if Self.funds.contains(p.symbol) { return false }
        return total > 0 && Double(p.value) / Double(total) > 0.2
    }

    private func holdingRow(_ p: Demo.Position) -> some View {
        let weight = total == 0 ? 0 : Int((Double(p.value) / Double(total) * 100).rounded())
        let conc = isConcentrated(p)
        let isCash = p.assetClass == "cash" || p.symbol == "CASH"
        return Button { if !isCash { onSelect(p) } } label: {
            HStack(spacing: 14) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(p.symbol).font(BrandFont.sansBold(16)).foregroundStyle(Color.inkPrimary)
                    Text(p.name).font(BrandFont.sans(13)).foregroundStyle(Color.inkTertiary).lineLimit(1)
                    if conc {
                        Text("\(weight)% of account")
                            .font(BrandFont.sansBold(11)).foregroundStyle(Color.attention)
                            .padding(.horizontal, 7).padding(.vertical, 2)
                            .background(RoundedRectangle(cornerRadius: 6).fill(Color.attention.opacity(0.12)))
                            .padding(.top, 3)
                    }
                }
                Spacer(minLength: 8)
                VStack(alignment: .trailing, spacing: 2) {
                    Text(usd(p.value)).font(BrandFont.sansBold(16)).foregroundStyle(Color.inkPrimary).monospacedDigit()
                    if !conc {
                        Text(isCash ? "cash" : "\(weight)% of account")
                            .font(BrandFont.sans(12)).foregroundStyle(Color.inkTertiary).monospacedDigit()
                    }
                }
            }
            .padding(.vertical, 12)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(isCash)
    }
}

// MARK: - Recurring / automatic investing card

struct RecurringCard: View {
    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "arrow.triangle.2.circlepath").font(.system(size: 18)).foregroundStyle(Color.allworthAccent).frame(width: 22)
            VStack(alignment: .leading, spacing: 1) {
                Text("Automatic investing").font(BrandFont.sansBold(16)).foregroundStyle(Color.inkPrimary)
                Text(Demo.recurringNext).font(BrandFont.sans(13)).foregroundStyle(Color.inkTertiary)
            }
            Spacer()
            Text(Demo.recurringMonthly).font(BrandFont.sansBold(16)).foregroundStyle(Color.inkPrimary).monospacedDigit()
            Image(systemName: "chevron.down").font(.system(size: 13, weight: .semibold)).foregroundStyle(Color.inkTertiary)
        }
        .padding(16)
        .card()
    }
}
