import SwiftUI

// "Beat 6" vision screen — 1:1 port of VisionScreen. Navy gradient, the loop
// diagram (Client Intelligence Layer + three nodes), four callouts, the path-to-
// production roadmap, and the closing line.
struct VisionView: View {
    private let callouts: [(String, String, String)] = [
        ("1", "Per-client learning", "Knows every client better every day"),
        ("2", "Cross-client patterns", "Every client benefits from patterns across the book — fully anonymized"),
        ("3", "System outcomes", "Measurably better every week it runs"),
        ("✓", "Provenance", "Every fact has a source, a timestamp, and an audit trail"),
    ]
    private let roadmap = ["Demo", "LLM chat", "Real data", "Briefs", "Memory", "Production"]

    var body: some View {
        GeometryReader { proxy in
            let safeTop = proxy.safeAreaInsets.top
            let safeBottom = proxy.safeAreaInsets.bottom
            VStack(spacing: 0) {
                VStack(spacing: 10) {
                    AllworthWordmark(light: true)
                    Text("What the funded platform becomes")
                        .font(BrandFont.sans(15)).foregroundStyle(.white.opacity(0.6))
                }
                .padding(.top, safeTop + 24)

                Spacer(minLength: 0)
                diagram
                Spacer(minLength: 0)

                VStack(alignment: .leading, spacing: 16) {
                    ForEach(callouts, id: \.0) { c in
                        HStack(alignment: .top, spacing: 12) {
                            ZStack {
                                Circle().fill(.white).frame(width: 22, height: 22)
                                Text(c.0).font(BrandFont.sansBold(13)).foregroundStyle(Color.allworthNavy)
                            }
                            VStack(alignment: .leading, spacing: 2) {
                                Text(c.1).font(BrandFont.sansBold(15)).foregroundStyle(.white)
                                Text(c.2).font(BrandFont.sans(13)).foregroundStyle(.white.opacity(0.65))
                            }
                            Spacer(minLength: 0)
                        }
                    }
                }
                .padding(.horizontal, 32)

                Spacer(minLength: 0)

                VStack(spacing: 8) {
                    Text("PATH TO PRODUCTION").font(BrandFont.sansBold(10)).tracking(1.2).foregroundStyle(.white.opacity(0.45))
                    HStack(spacing: 2) {
                        ForEach(Array(roadmap.enumerated()), id: \.offset) { i, label in
                            let today = i == 0
                            Text(label)
                                .font(BrandFont.sansBold(11)).foregroundStyle(today ? Color.allworthNavy : .white.opacity(0.75))
                                .fixedSize()
                                .padding(.horizontal, 8).padding(.vertical, 4)
                                .background(Capsule().fill(today ? Color.white : .clear)
                                    .overlay(Capsule().stroke(.white.opacity(today ? 0 : 0.25), lineWidth: 1)))
                            if i < roadmap.count - 1 {
                                Image(systemName: "chevron.right").font(.system(size: 9)).foregroundStyle(.white.opacity(0.35))
                            }
                        }
                    }
                }
                .padding(.horizontal, 16)

                Spacer(minLength: 0)

                Text("Models are rented. This memory is owned — and it compounds.")
                    .font(BrandFont.displayItalic(19)).foregroundStyle(.white)
                    .multilineTextAlignment(.center).lineSpacing(4)
                    .padding(.horizontal, 40)
                    .padding(.bottom, safeBottom + 36)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(
            LinearGradient(colors: [.nightBlue, .allworthNavy], startPoint: .top, endPoint: .bottom)
                .ignoresSafeArea()
        )
    }

    private var diagram: some View {
        ZStack {
            Circle().stroke(style: StrokeStyle(lineWidth: 1, dash: [4, 5]))
                .foregroundStyle(.white.opacity(0.18)).frame(width: 260, height: 260)
            VStack(spacing: 6) {
                Image(systemName: "lightbulb").font(.system(size: 30)).foregroundStyle(.white)
                Text("Client Intelligence\nLayer").font(BrandFont.sansBold(15)).foregroundStyle(.white).multilineTextAlignment(.center)
                HStack(spacing: 4) {
                    Image(systemName: "clock").font(.system(size: 11)).foregroundStyle(.white.opacity(0.55))
                    Text("nightly job").font(BrandFont.sans(11)).foregroundStyle(.white.opacity(0.55))
                }
            }
            .frame(width: 150, height: 150)
            .background(Circle().fill(.white.opacity(0.08)))
            ForEach([("1", -90.0), ("2", 30.0), ("3", 150.0)], id: \.0) { node in
                let r = 130.0
                ZStack {
                    Circle().fill(.white).frame(width: 34, height: 34)
                    Text(node.0).font(BrandFont.sansBold(15)).foregroundStyle(Color.allworthNavy)
                }
                .offset(x: r * cos(node.1 * .pi / 180), y: r * sin(node.1 * .pi / 180))
            }
        }
        .frame(height: 290)
    }
}
