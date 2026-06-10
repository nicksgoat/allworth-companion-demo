import SwiftUI

struct HeroNumberView: View {
    let label: String
    let value: Int
    var delta: (text: String, positive: Bool)?

    @State private var displayed = 0

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).sectionHeaderStyle()
            Text(displayed.usd)
                .font(Theme.hero)
                .foregroundStyle(Theme.inkPrimary)
                .monospacedDigit()
                .contentTransition(.numericText(value: Double(displayed)))
            if let delta {
                Text(delta.text)
                    .font(Theme.number(15))
                    .foregroundStyle(delta.positive ? Theme.gainGreen : Theme.lossRed)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .onAppear {
            displayed = Int(Double(value) * 0.97)
            withAnimation(.spring(response: 0.55, dampingFraction: 0.9)) { displayed = value }
        }
        .onChange(of: value) { _, new in
            withAnimation(Theme.spring) { displayed = new }
        }
    }
}

#Preview {
    HeroNumberView(label: "Net worth", value: 2_746_000, delta: ("-$7,770 this month", false))
        .padding(20)
        .background(Theme.surfacePrimary)
}
