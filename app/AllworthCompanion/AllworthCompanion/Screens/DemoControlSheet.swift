import SwiftUI

/// Hidden demo control bar — opened by triple-tapping the Allworth wordmark.
struct DemoControlSheet: View {
    @Environment(AppState.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var resetDone = false

    var body: some View {
        @Bindable var app = app
        NavigationStack {
            Form {
                Section("View") {
                    Picker("Mode", selection: $app.mode) {
                        ForEach(AppState.Mode.allCases, id: \.self) { mode in
                            Text(mode.rawValue).tag(mode)
                        }
                    }
                    .pickerStyle(.segmented)
                }
                Section("Session") {
                    Picker("Session", selection: $app.session) {
                        Text("Monday (first chat)").tag("monday")
                        Text("Wednesday (memory)").tag("wednesday")
                    }
                    .pickerStyle(.segmented)
                }
                Section("Backend") {
                    TextField("Host", text: $app.backendHost)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                }
                Section {
                    Button(role: .destructive) {
                        Task {
                            await app.resetDemo()
                            resetDone = true
                        }
                    } label: {
                        HStack {
                            Text("Reset demo")
                            Spacer()
                            if resetDone { Image(systemName: "checkmark.circle.fill").foregroundStyle(.green) }
                        }
                    }
                } footer: {
                    Text("Clears conversation state and re-seeds Maya's Monday profile.")
                }
            }
            .navigationTitle("Demo controls")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .presentationDetents([.medium])
    }
}
