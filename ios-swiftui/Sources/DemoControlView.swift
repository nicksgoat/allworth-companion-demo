import SwiftUI

// Hidden demo control sheet — opened by triple-tapping the header mark (RN
// DemoControlSheet). Switches View (Client / Advisor / Vision) and the chat
// Session, with a backend-host field and a reset, both cosmetic in this copy.
struct DemoControlView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var host = "allworth-demo.fly.dev"
    @State private var resetDone = false

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Demo controls").font(BrandFont.sansBold(17)).foregroundStyle(Color.inkPrimary)
                Spacer()
                Button("Done") { dismiss() }
                    .font(BrandFont.sansBold(17)).foregroundStyle(Color.allworthAccent)
            }
            .padding(.horizontal, 20).padding(.top, 18)

            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    section("View") {
                        segmented(["Client", "Advisor", "Vision"], selected: viewLabel) { pick in
                            switch pick {
                            case "Advisor": app.mode = .advisor
                            case "Vision": app.mode = .vision
                            default: app.mode = .client
                            }
                            dismiss()
                        }
                    }
                    section("Session") {
                        segmented(["Monday (first chat)", "Wednesday (memory)"],
                                  selected: app.session == "monday" ? "Monday (first chat)" : "Wednesday (memory)") { pick in
                            app.session = pick.hasPrefix("Monday") ? "monday" : "wednesday"
                        }
                    }
                    section("Backend") {
                        TextField("Host", text: $host)
                            .font(BrandFont.sans(17)).foregroundStyle(Color.inkPrimary)
                            .textInputAutocapitalization(.never).autocorrectionDisabled()
                            .padding(.horizontal, 14).padding(.vertical, 12)
                            .card()
                    }
                    VStack(alignment: .leading, spacing: 8) {
                        Button { withAnimation { resetDone = true } } label: {
                            HStack {
                                Text("Reset demo").font(BrandFont.sans(17)).foregroundStyle(Color.loss)
                                Spacer()
                                if resetDone {
                                    Image(systemName: "checkmark.circle.fill").font(.system(size: 18)).foregroundStyle(Color.gain)
                                }
                            }
                            .padding(.horizontal, 16).padding(.vertical, 13)
                            .card()
                        }
                        .buttonStyle(.plain)
                        Text("Clears conversation state and re-seeds Maya's Monday profile.")
                            .font(BrandFont.sans(13)).foregroundStyle(Color.inkTertiary)
                    }
                }
                .padding(20)
            }
        }
        .background(Color.surfacePrimary.ignoresSafeArea())
    }

    private var viewLabel: String {
        switch app.mode { case .advisor: return "Advisor"; case .vision: return "Vision"; case .client: return "Client" }
    }

    private func section<C: View>(_ header: String, @ViewBuilder _ content: () -> C) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionHeader(header)
            content()
        }
    }

    private func segmented(_ options: [String], selected: String, onPick: @escaping (String) -> Void) -> some View {
        HStack(spacing: 0) {
            ForEach(options, id: \.self) { opt in
                let active = opt == selected
                Text(opt)
                    .font(active ? BrandFont.sansBold(13) : BrandFont.sans(13))
                    .foregroundStyle(active ? Color.inkPrimary : Color.inkSecondary)
                    .lineLimit(1).minimumScaleFactor(0.8)
                    .frame(maxWidth: .infinity).padding(.vertical, 7)
                    .background(RoundedRectangle(cornerRadius: 7).fill(active ? Color.white : .clear)
                        .shadow(color: active ? Color.nightBlue.opacity(0.06) : .clear, radius: 3, y: 1))
                    .contentShape(Rectangle())
                    .onTapGesture { onPick(opt) }
            }
        }
        .padding(2)
        .background(RoundedRectangle(cornerRadius: 9).fill(Color.inkFaint))
    }
}
