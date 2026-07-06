import SwiftUI

// Chat — light glass header (no navy hero; a hero would eat the conversation),
// the assistant thread, suggestion chips, and the composer. Ported from
// ChatScreen + components/Chat: user bubbles right in gray, assistant as bare
// markdown text, a "thinking" beat before each answer, thumbs + follow-up chips.
// No backend, so answers are canned but the send/reply flow is real.

struct ChatMsg: Identifiable {
    let id = UUID()
    var role: Role
    var text: String
    var sources: [String] = []
    var thinking = false
    var thinkingLabel = "Thinking…"
    enum Role { case user, assistant }
}

struct ChatView: View {
    @Environment(AppModel.self) private var app
    @State private var messages: [ChatMsg] = [
        ChatMsg(role: .assistant, text: "Welcome back, Maya. I've refreshed your full picture — plan, portfolio, and goals. A couple of things stand out worth a closer look. Where would you like to start?"),
    ]
    @State private var draft = ""
    @State private var sending = false
    @State private var lastTopic = "start"
    @State private var dynamicChips: [String] = []
    @State private var streamTask: Task<Void, Never>?

    var body: some View {
        GeometryReader { proxy in
            let safeTop = proxy.safeAreaInsets.top
            ZStack(alignment: .top) {
                Color.surfacePrimary.ignoresSafeArea()

                ScrollViewReader { sr in
                    ScrollView(showsIndicators: false) {
                        VStack(alignment: .leading, spacing: Space.s5) {
                            sessionDivider
                            ForEach(messages) { m in
                                MessageBubble(m: m).id(m.id)
                            }
                            if !sending, let chips = suggestions {
                                SuggestionChips(items: chips) { send($0) }
                            }
                            Color.clear.frame(height: 1).id("bottom")
                        }
                        .padding(.horizontal, Space.s5)
                        .padding(.top, safeTop + 48 + Space.s4)
                        .padding(.bottom, Space.s4)
                    }
                    .ignoresSafeArea(edges: .top)
                    .safeAreaInset(edge: .bottom) { composer }
                    .onChange(of: messages.count) { _, _ in
                        withAnimation { sr.scrollTo("bottom", anchor: .bottom) }
                    }
                    .onChange(of: messages.last?.text) { _, _ in
                        sr.scrollTo("bottom", anchor: .bottom)
                    }
                }

                GlassHeader(title: "Nicole's Assistant", safeTop: safeTop, actionIconOverride: "square.and.pencil", onNewChat: newChat)
            }
        }
        .task {
            if ProcessInfo.processInfo.environment["AUTO_CHAT"] == "1", messages.count == 1 {
                send("How does this spending affect my plan?")
            }
            consumePending()
        }
        .onChange(of: app.pendingChatSend) { _, _ in consumePending() }
    }

    // A question handed over from another tab (e.g. Home's "Ask about spending").
    private func consumePending() {
        guard let q = app.pendingChatSend else { return }
        app.pendingChatSend = nil
        send(q)
    }

    private var sessionDivider: some View {
        HStack {
            Rectangle().fill(Color.hairline).frame(height: 1)
            Text("Wednesday, June 10").font(BrandFont.sansBold(12)).foregroundStyle(Color.inkTertiary).fixedSize()
            Rectangle().fill(Color.hairline).frame(height: 1)
        }
    }

    private var composer: some View {
        HStack(alignment: .bottom, spacing: 6) {
            TextField("Ask Allworth…", text: $draft, axis: .vertical)
                .font(BrandFont.sans(17)).foregroundStyle(Color.inkPrimary)
                .padding(.leading, 10).padding(.vertical, 8)
                .lineLimit(1...5)
            if !draft.trimmingCharacters(in: .whitespaces).isEmpty {
                Button { send(draft) } label: {
                    Image(systemName: "arrow.up").font(.system(size: 20, weight: .semibold)).foregroundStyle(.white)
                        .frame(width: 34, height: 34).background(Circle().fill(Color.allworthNavy))
                }
                .disabled(sending).opacity(sending ? 0.5 : 1)
            }
        }
        .padding(5)
        .glassEffect(.regular, in: Capsule())
        .padding(.horizontal, Space.s4)
        .padding(.bottom, Space.s2)
    }

    // Follow-up chips: the backend's real suggestions when live; topic-keyed
    // fallbacks when offline (RN dynamicSuggestions).
    private var suggestions: [String]? {
        guard messages.last?.role == .assistant, !(messages.last?.thinking ?? false) else { return nil }
        if !dynamicChips.isEmpty { return dynamicChips }
        switch lastTopic {
        case "spending": return ["What spending level keeps the plan on track?", "Which categories are driving the overage?", "How does this affect the lake house timeline?"]
        case "concentration": return ["Show the tax impact in plain English", "Which holdings would be sold first?", "What if we limit realized gains?"]
        case "start": return ["How does this spending affect my plan?", "What are my options for NVDA?", "What are my options for TSLA?"]
        default: return nil    // "live" answer with no backend suggestions
        }
    }

    private func send(_ text: String) {
        let q = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty, !sending else { return }
        draft = ""
        sending = true
        dynamicChips = []
        messages.append(ChatMsg(role: .user, text: q))
        messages.append(ChatMsg(role: .assistant, text: "", thinking: true))
        let idx = messages.count - 1     // the streaming assistant bubble

        streamTask?.cancel()
        streamTask = Task {
            var gotText = false
            for await ev in ChatService.stream(clientId: "maya", session: app.session, message: q) {
                if Task.isCancelled { return }
                switch ev {
                case .toolStart(let label):
                    if idx < messages.count { messages[idx].thinkingLabel = label }
                case .toolEnd:
                    break
                case .text(let delta):
                    guard idx < messages.count else { break }
                    if !gotText { gotText = true; lastTopic = "live"; messages[idx].thinking = false; messages[idx].text = "" }
                    messages[idx].text += delta
                case .done(let sources, let suggested):
                    guard idx < messages.count else { break }
                    messages[idx].thinking = false
                    messages[idx].sources = sources
                    dynamicChips = suggested
                case .error:
                    // Backend unreachable — fall back to the offline canned answer.
                    guard idx < messages.count, !gotText else { break }
                    let (answer, sources, topic) = reply(to: q)
                    withAnimation(.easeOut(duration: 0.3)) {
                        messages[idx].thinking = false
                        messages[idx].text = answer
                        messages[idx].sources = sources
                    }
                    lastTopic = topic
                }
            }
            sending = false
        }
    }

    private func newChat() {
        streamTask?.cancel()
        messages = [ChatMsg(role: .assistant, text: "Hi Maya — I can help you understand your accounts, spending, or plan. What's on your mind?")]
        lastTopic = "start"
        dynamicChips = []
        draft = ""; sending = false
    }

    private func reply(to q: String) -> (String, [String], String) {
        let l = q.lowercased()
        if l.contains("spending") || l.contains("plan on track") || l.contains("overage") || l.contains("lake house") {
            return ("Your spending has run about **18% over plan** the last three months — roughly $16,500/mo against your $14,000 plan. Most of the gap is **Travel** and **Gifts/Family**. On its own it's manageable, but if it keeps up it pushes the lake-house timeline out by a few months. Want me to show the monthly number that keeps the plan on track?", ["Spending analysis", "Financial plan"], "spending")
        }
        if l.contains("nvda") {
            return ("NVDA is about **54% of your Robinhood account** ($52,080). That one position drives most of the account's swings. A few ways to trim it over time — selling in tax-aware lots or offsetting with losses elsewhere. It's low-basis, so there's capital-gains tax to weigh. I can model trimming it to, say, 25%.", ["Portfolio analysis", "Tax impact"], "concentration")
        }
        if l.contains("tsla") {
            return ("TSLA is about **26% of your Robinhood account** ($24,890) — smaller than NVDA but still concentrated. Same playbook: trim gradually and tax-aware. Want to see what selling half would look like after tax?", ["Portfolio analysis", "Tax impact"], "concentration")
        }
        if l.contains("tax") || l.contains("sold first") || l.contains("realized gains") {
            return ("In plain English: selling the newest, highest-cost lots first realizes the **least** gain, so the tax bill stays small. We'd sell short-term-loss lots first, then long-term lots up to a gain limit you set. On your Robinhood positions that keeps most of the trim in low-tax territory.", ["Tax impact"], "concentration")
        }
        return ("Happy to help with that. I can look at your accounts, spending, or plan and walk it through in plain English. What would you like to dig into?", [], "default")
    }
}

private struct MessageBubble: View {
    let m: ChatMsg
    @State private var vote = 0   // 0 none · 1 up · -1 down
    var body: some View {
        switch m.role {
        case .user:
            HStack {
                Spacer(minLength: 48)
                Text(m.text).font(BrandFont.sans(17)).foregroundStyle(Color.inkPrimary)
                    .padding(.horizontal, 14).padding(.vertical, 10)
                    .background(RoundedRectangle(cornerRadius: 16).fill(Color.inkFaint))
            }
        case .assistant:
            if m.thinking {
                ThinkingDots(label: m.thinkingLabel)
            } else {
                VStack(alignment: .leading, spacing: Space.s3) {
                    if !m.sources.isEmpty {
                        HStack(spacing: 6) {
                            Image(systemName: "magnifyingglass").font(.system(size: 12)).foregroundStyle(Color.inkTertiary)
                            Text("Sources: \(m.sources.joined(separator: " · "))")
                                .font(BrandFont.sans(13)).foregroundStyle(Color.inkTertiary)
                        }
                    }
                    Text(boldMarkdown(m.text)).font(BrandFont.sans(17)).foregroundStyle(Color.inkPrimary).lineSpacing(6)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    HStack(spacing: Space.s4) {
                        Button { vote = vote == 1 ? 0 : 1 } label: {
                            Image(systemName: vote == 1 ? "hand.thumbsup.fill" : "hand.thumbsup")
                                .foregroundStyle(vote == 1 ? Color.allworthAccent : Color.inkTertiary)
                        }.buttonStyle(.plain)
                        Button { vote = vote == -1 ? 0 : -1 } label: {
                            Image(systemName: vote == -1 ? "hand.thumbsdown.fill" : "hand.thumbsdown")
                                .foregroundStyle(vote == -1 ? Color.allworthAccent : Color.inkTertiary)
                        }.buttonStyle(.plain)
                        Spacer()
                    }
                    .font(.system(size: 15))
                }
                .transition(.opacity)
            }
        }
    }
}

private struct ThinkingDots: View {
    var label: String = "Thinking…"
    @State private var on = false
    var body: some View {
        HStack(spacing: 8) {
            HStack(spacing: 5) {
                ForEach(0..<3) { i in
                    Circle().fill(Color.allworthAccent).frame(width: 7, height: 7)
                        .opacity(on ? 1 : 0.3)
                        .animation(.easeInOut(duration: 0.6).repeatForever().delay(Double(i) * 0.18), value: on)
                }
            }
            Text(label).font(BrandFont.sans(14)).foregroundStyle(Color.inkTertiary)
            Spacer()
        }
        .onAppear { on = true }
    }
}

private struct SuggestionChips: View {
    let items: [String]
    let onPick: (String) -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: Space.s2) {
            ForEach(items, id: \.self) { s in
                Button { onPick(s) } label: {
                    Text(s).font(BrandFont.sans(15)).foregroundStyle(Color.inkSecondary)
                        .padding(.horizontal, Space.s3).padding(.vertical, 6)
                        .glassEffect(.regular.interactive(), in: Capsule())
                }
                .buttonStyle(.plain)
            }
        }
    }
}

// Render **bold** spans (the only markdown the demo answers use).
func boldMarkdown(_ s: String) -> AttributedString {
    var out = AttributedString()
    let parts = s.components(separatedBy: "**")
    for (i, part) in parts.enumerated() {
        var a = AttributedString(part)
        a.font = i % 2 == 1 ? .custom("Lato-Bold", size: 17) : .custom("Lato-Regular", size: 17)
        out += a
    }
    return out
}

// Chat header: mark + title + compose (new chat).
extension GlassHeader {
    init(title: String, safeTop: CGFloat, actionIconOverride: String, onNewChat: (() -> Void)? = nil) {
        self.init(title: title, scrollY: 0, onHero: false, heroReveal: false,
                  actionIcon: actionIconOverride, onAction: onNewChat, safeTop: safeTop)
    }
}
