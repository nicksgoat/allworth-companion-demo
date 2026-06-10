import SwiftUI

struct ChatView: View {
    @Environment(AppState.self) private var app
    @State private var draft = ""
    @State private var sending = false

    var body: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 24) {
                        ForEach(app.chatMessages) { message in
                            ChatMessageView(message: message).id(message.id)
                        }
                    }
                    .padding(20)
                }
                .onChange(of: app.chatMessages.last?.text) { _, _ in
                    if let id = app.chatMessages.last?.id {
                        proxy.scrollTo(id, anchor: .bottom)
                    }
                }
                .onChange(of: app.chatMessages.count) { _, _ in
                    if let id = app.chatMessages.last?.id {
                        withAnimation(Theme.spring) { proxy.scrollTo(id, anchor: .bottom) }
                    }
                }
            }
            inputBar
        }
        .background(Theme.surfacePrimary)
        .task { await loadProactive() }
        .onChange(of: app.session) { _, _ in Task { await loadProactive() } }
        .onAppear {
            if let prefill = app.chatPrefill {
                draft = prefill
                app.chatPrefill = nil
            }
        }
        .onChange(of: app.chatPrefill) { _, prefill in
            if let prefill {
                draft = prefill
                app.chatPrefill = nil
            }
        }
    }

    private var inputBar: some View {
        VStack(spacing: 8) {
            DisclaimerFooter()
            HStack(spacing: 10) {
                TextField("Ask about your money…", text: $draft, axis: .vertical)
                    .font(Theme.body)
                    .lineLimit(1...4)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .onSubmit(send)
                Button(action: send) {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.system(size: 30))
                        .foregroundStyle(canSend ? Theme.allworthAccent : Theme.inkTertiary)
                }
                .buttonStyle(.plain)
                .disabled(!canSend)
                .padding(.trailing, 6)
            }
            .cardStyle()
        }
        .padding(.horizontal, 20)
        .padding(.top, 6)
        .padding(.bottom, 10)
        .background(Theme.surfacePrimary)
    }

    private var canSend: Bool {
        !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !sending
    }

    private func loadProactive() async {
        guard app.chatMessages.isEmpty else { return }
        let greeting: String
        if let response = try? await app.api.proactive(clientId: app.clientId, session: app.session) {
            greeting = response.message
        } else {
            greeting = "Hi Maya — I can help you understand your accounts, spending, or plan. What's on your mind?"
        }
        guard app.chatMessages.isEmpty else { return }
        app.chatMessages.append(ChatMessage(role: .assistant, text: greeting))
    }

    private func send() {
        guard canSend else { return }
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        draft = ""
        sending = true
        app.chatMessages.append(ChatMessage(role: .user, text: text))
        app.chatMessages.append(ChatMessage(role: .assistant, text: "", isStreaming: true))

        Task {
            for await event in await app.api.chat(clientId: app.clientId, session: app.session, message: text) {
                apply(event)
            }
            withAnimation(Theme.spring) {
                if var last = app.chatMessages.last {
                    last.isStreaming = false
                    last.chips = last.chips.map { ToolChip(name: $0.name, label: $0.label, running: false) }
                    app.chatMessages[app.chatMessages.count - 1] = last
                }
            }
            sending = false
        }
    }

    private func apply(_ event: ChatEvent) {
        guard var last = app.chatMessages.last, last.role == .assistant else { return }
        switch event {
        case .toolStart(let name, let label):
            withAnimation(Theme.spring) {
                last.chips.append(ToolChip(name: name, label: label, running: true))
                app.chatMessages[app.chatMessages.count - 1] = last
            }
        case .toolEnd(let name):
            if let index = last.chips.firstIndex(where: { $0.name == name }) {
                last.chips[index].running = false
                app.chatMessages[app.chatMessages.count - 1] = last
            }
        case .text(let delta):
            last.text += delta
            app.chatMessages[app.chatMessages.count - 1] = last
        case .done(let sources, _):
            withAnimation(Theme.spring) {
                last.sources = sources
                last.isStreaming = false
                app.chatMessages[app.chatMessages.count - 1] = last
            }
        case .error(let message):
            last.text = message
            last.isStreaming = false
            app.chatMessages[app.chatMessages.count - 1] = last
        }
    }
}
