import SwiftUI

/// Beat 6 — static vision screen: "What the funded platform becomes."
struct VisionView: View {
    @Environment(AppState.self) private var app
    @State private var appeared = false

    var body: some View {
        ZStack {
            Theme.allworthNavy.ignoresSafeArea()

            VStack(spacing: 0) {
                AllworthWordmark(light: true)
                    .padding(.top, 24)

                Text("What the funded platform becomes")
                    .font(Theme.secondary)
                    .foregroundStyle(.white.opacity(0.6))
                    .padding(.top, 10)

                Spacer()

                // Central memory store with the three loops around it
                ZStack {
                    Circle()
                        .stroke(.white.opacity(0.18), style: StrokeStyle(lineWidth: 1, dash: [4, 6]))
                        .frame(width: 260, height: 260)
                    VStack(spacing: 6) {
                        Image(systemName: "brain")
                            .font(.system(size: 30))
                            .foregroundStyle(.white)
                        Text("Client Intelligence\nLayer")
                            .font(.system(size: 15, weight: .semibold))
                            .multilineTextAlignment(.center)
                            .foregroundStyle(.white)
                        Label("nightly job", systemImage: "clock")
                            .font(.system(size: 11))
                            .foregroundStyle(.white.opacity(0.55))
                    }
                    .frame(width: 150, height: 150)
                    .background(.white.opacity(0.08), in: Circle())

                    loopNode("1", angle: -90)
                    loopNode("2", angle: 30)
                    loopNode("3", angle: 150)
                }
                .frame(height: 290)
                .scaleEffect(appeared ? 1 : 0.92)
                .opacity(appeared ? 1 : 0)

                VStack(alignment: .leading, spacing: 16) {
                    callout("1", "Per-client learning", "Knows every client better every day")
                    callout("2", "Cross-client patterns", "Every client benefits from patterns across the book — fully anonymized")
                    callout("3", "System outcomes", "Measurably better every week it runs")
                    callout("✓", "Provenance", "Every fact has a source, a timestamp, and an audit trail")
                }
                .padding(.horizontal, 32)
                .padding(.top, 28)
                .opacity(appeared ? 1 : 0)

                Spacer()

                Text("Models are rented. This memory is owned — and it compounds.")
                    .font(.system(size: 19, weight: .semibold, design: .serif))
                    .italic()
                    .foregroundStyle(.white)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 40)
                    .padding(.bottom, 36)
                    .opacity(appeared ? 1 : 0)
            }
        }
        .onAppear {
            withAnimation(.spring(response: 0.7, dampingFraction: 0.85)) { appeared = true }
        }
    }

    private func loopNode(_ number: String, angle: Double) -> some View {
        let radians = angle * .pi / 180
        return Circle()
            .fill(.white)
            .frame(width: 34, height: 34)
            .overlay {
                Text(number)
                    .font(.system(size: 15, weight: .bold, design: .rounded))
                    .foregroundStyle(Theme.allworthNavy)
            }
            .offset(x: 130 * cos(radians), y: 130 * sin(radians))
    }

    private func callout(_ marker: String, _ title: String, _ detail: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Text(marker)
                .font(.system(size: 13, weight: .bold, design: .rounded))
                .foregroundStyle(Theme.allworthNavy)
                .frame(width: 22, height: 22)
                .background(.white, in: Circle())
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(.white)
                Text(detail)
                    .font(.system(size: 13))
                    .foregroundStyle(.white.opacity(0.65))
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}
