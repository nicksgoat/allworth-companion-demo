import SwiftUI
import Charts

struct SparklineChart: View {
    let points: [MonthValue]
    var lineColor: Color = Theme.allworthNavy

    @State private var selected: MonthValue?

    var body: some View {
        Chart(points) { point in
            // yStart pins the fill to the visible domain floor; without it the
            // area extends to y=0, hundreds of points below the chart frame.
            AreaMark(x: .value("Month", point.month),
                     yStart: .value("Base", yDomain.lowerBound),
                     yEnd: .value("Value", point.value))
                .interpolationMethod(.catmullRom)
                .foregroundStyle(
                    LinearGradient(colors: [lineColor.opacity(0.14), .clear],
                                   startPoint: .top, endPoint: .bottom))
            LineMark(x: .value("Month", point.month), y: .value("Value", point.value))
                .lineStyle(StrokeStyle(lineWidth: 2))
                .foregroundStyle(lineColor)
                .interpolationMethod(.catmullRom)
            if let selected, selected.month == point.month {
                PointMark(x: .value("Month", point.month), y: .value("Value", point.value))
                    .symbolSize(60)
                    .foregroundStyle(lineColor)
            }
        }
        .chartXAxis(.hidden)
        .chartYAxis(.hidden)
        .chartYScale(domain: yDomain)
        .chartPlotStyle { $0.clipped() }
        .chartOverlay { proxy in
            GeometryReader { _ in
                Rectangle().fill(.clear).contentShape(Rectangle())
                    .gesture(
                        DragGesture(minimumDistance: 0)
                            .onChanged { drag in
                                if let month: String = proxy.value(atX: drag.location.x) {
                                    selected = points.first { $0.month == month }
                                }
                            }
                            .onEnded { _ in
                                withAnimation(Theme.spring) { selected = nil }
                            }
                    )
            }
        }
        .overlay(alignment: .topLeading) {
            if let selected {
                Text("\(selected.value.usd)  ·  \(Self.monthLabel(selected.month))")
                    .font(Theme.number(13))
                    .foregroundStyle(Theme.inkSecondary)
                    .transition(.opacity)
            }
        }
        .sensoryFeedback(.impact(weight: .light), trigger: selected?.month)
        .frame(height: 88)
    }

    /// "2025-11" → "Nov 2025"
    private static func monthLabel(_ month: String) -> String {
        let parts = month.split(separator: "-")
        guard parts.count == 2, let m = Int(parts[1]), (1...12).contains(m) else { return month }
        return Calendar.current.shortMonthSymbols[m - 1] + " " + parts[0]
    }

    private var yDomain: ClosedRange<Int> {
        let values = points.map(\.value)
        guard let lo = values.min(), let hi = values.max(), lo != hi else { return 0...1 }
        let pad = (hi - lo) / 4
        return (lo - pad)...(hi + pad)
    }
}
