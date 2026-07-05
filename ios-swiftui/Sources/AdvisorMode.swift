import SwiftUI

// Advisor mode — 1:1 port of AdvisorScreens + AdvisorConversationScreen. A
// NavigationStack: Book (household list) → ClientDetail (glance strip, live-
// conversation preview, auto-prepared brief, outside accounts) → the full
// conversation with advisor interject.
struct AdvisorRootView: View {
    @State private var path = NavigationPath()
    var body: some View {
        NavigationStack(path: $path) {
            BookView()
                .navigationDestination(for: Demo.Household.self) { ClientDetailView(household: $0) }
                .navigationDestination(for: Demo.ConvRef.self) { ClientConversationView(convo: $0) }
        }
        .tint(.allworthNavy)
        .onAppear {
            let maya = Demo.book[0]
            switch ProcessInfo.processInfo.environment["ADVISOR_SCREEN"] {
            case "detail": path.append(maya)
            case "conversation":
                path.append(maya)
                path.append(Demo.ConvRef(clientId: maya.id, clientName: "Maya"))
            default: break
            }
        }
    }
}

// MARK: - Book

private struct BookView: View {
    @Environment(AppModel.self) private var app
    @State private var scrollY: CGFloat = 0
    @State private var appeared = false

    var body: some View {
        GeometryReader { proxy in
            let safeTop = proxy.safeAreaInsets.top
            ZStack(alignment: .top) {
                Color.surfacePrimary.ignoresSafeArea()
                ScrollView(showsIndicators: false) {
                    VStack(spacing: 0) {
                        NavyHeroBand(safeTop: safeTop) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(Demo.advisorName).font(BrandFont.displayMedium(26)).foregroundStyle(.white)
                                Text(Demo.advisorTitle).font(BrandFont.sans(13)).foregroundStyle(.white.opacity(0.72))
                            }
                            .entrance(0.1, appeared: appeared)
                        }
                        VStack(spacing: 0) {
                            ForEach(Array(Demo.book.enumerated()), id: \.element.id) { i, h in
                                if i > 0 { Hairline() }
                                NavigationLink(value: h) { HouseholdRow(h: h) }.buttonStyle(.plain)
                            }
                            DisclaimerFooter().padding(.top, Space.s4)
                        }
                        .padding(.horizontal, Space.s5)
                        .padding(.top, Space.s5)
                        .padding(.bottom, Space.s8)
                        .entrance(0.2, appeared: appeared)
                    }
                }
                .trackScroll(into: $scrollY)
                .ignoresSafeArea(edges: .top)

                GlassHeader(title: "Your book", scrollY: scrollY, onHero: true,
                            actionIcon: "arrow.left.arrow.right", onAction: { app.advisorMode = false }, safeTop: safeTop)
            }
        }
        .toolbar(.hidden, for: .navigationBar)
        .onAppear { appeared = true }
    }
}

private struct HouseholdRow: View {
    let h: Demo.Household
    private var initials: String {
        h.name.split(separator: " ").filter { $0.first?.isLetter == true }
            .prefix(2).compactMap { $0.first }.map(String.init).joined().uppercased()
    }
    var body: some View {
        HStack(spacing: 12) {
            ZStack {
                Circle().fill(h.highlight ? Color.allworthNavy : Color.inkFaint).frame(width: 40, height: 40)
                Text(initials).font(BrandFont.sansBold(14)).foregroundStyle(h.highlight ? .white : Color.inkSecondary)
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(h.name).font(h.highlight ? BrandFont.sansBold(17) : BrandFont.sans(17)).foregroundStyle(Color.inkPrimary)
                HStack(spacing: 8) {
                    Text("\(usd(h.managed)) managed").font(BrandFont.sans(13)).foregroundStyle(Color.inkTertiary)
                    if h.heldAway > 0 {
                        Text("\(usd(h.heldAway)) held away").font(BrandFont.sansBold(13)).foregroundStyle(Color.allworthAccent)
                    }
                }
            }
            Spacer(minLength: 8)
            if h.openNudges > 0 {
                Text("\(h.openNudges)").font(BrandFont.sansBold(13)).foregroundStyle(.white)
                    .frame(width: 22, height: 22).background(Circle().fill(Color.attention))
            }
            Image(systemName: "chevron.right").font(.system(size: 14, weight: .semibold)).foregroundStyle(Color.inkTertiary)
        }
        .padding(.vertical, 12)
        .contentShape(Rectangle())
    }
}

// MARK: - Client detail

private struct ClientDetailView: View {
    let household: Demo.Household

    var body: some View {
        ScrollView {
            VStack(spacing: 24) {
                statStrip
                ConversationPreviewCard(household: household)
                CollapsibleCardView(icon: "sparkles", title: "Auto-prepared brief", preview: Demo.briefNarrative[0]) {
                    VStack(alignment: .leading, spacing: 12) {
                        ForEach(Demo.briefNarrative.dropFirst().indices, id: \.self) { i in
                            Text(Demo.briefNarrative[i]).font(BrandFont.sans(15)).foregroundStyle(Color.inkPrimary).lineSpacing(6)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                }
                CollapsibleCardView(icon: "wallet.bifold", title: "Outside accounts · \(Demo.briefOutsideAccounts.count)", preview: "") {
                    VStack(spacing: 0) {
                        ForEach(Array(Demo.briefOutsideAccounts.enumerated()), id: \.element.id) { i, a in
                            if i > 0 { Hairline() }
                            HStack {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(a.name).font(BrandFont.sans(17)).foregroundStyle(Color.inkPrimary)
                                    Text(a.institution).font(BrandFont.sans(13)).foregroundStyle(Color.inkTertiary)
                                }
                                Spacer()
                                Text(usd(a.balance)).font(BrandFont.sansBold(17)).foregroundStyle(a.balance < 0 ? Color.loss : Color.inkPrimary).monospacedDigit()
                            }
                            .padding(.vertical, 12)
                        }
                    }
                }
                DisclaimerFooter().padding(.vertical, 8)
            }
            .padding(20)
        }
        .background(Color.surfacePrimary.ignoresSafeArea())
        .navigationTitle(household.name)
        .navigationBarTitleDisplayMode(.inline)
    }

    private var statStrip: some View {
        HStack(spacing: 0) {
            stat("Managed", usd(household.managed), .inkPrimary)
            divider
            stat("Held away", usd(household.heldAway), .allworthAccent)
            divider
            stat("Open items", "\(household.openNudges)", household.openNudges > 0 ? .attention : .inkPrimary)
        }
        .padding(.vertical, 12).padding(.horizontal, 8)
        .card()
    }
    private var divider: some View { Rectangle().fill(Color.hairline).frame(width: 1).frame(maxHeight: .infinity) }
    private func stat(_ label: String, _ value: String, _ color: Color) -> some View {
        VStack(spacing: 2) {
            Text(value).font(BrandFont.sansBold(17)).foregroundStyle(color).monospacedDigit()
            Text(label.uppercased()).font(BrandFont.sans(11)).tracking(0.3).foregroundStyle(Color.inkTertiary)
        }
        .frame(maxWidth: .infinity)
    }
}

private struct ConversationPreviewCard: View {
    let household: Demo.Household
    private var clientName: String { String(household.name.split(separator: ",")[0].split(separator: " ")[0]) }
    private var recent: [Demo.ConvMsg] { Array(Demo.conversation.suffix(3)) }

    var body: some View {
        NavigationLink(value: Demo.ConvRef(clientId: household.id, clientName: clientName)) {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 8) {
                    Image(systemName: "bubble.left.and.bubble.right").font(.system(size: 13)).foregroundStyle(Color.allworthAccent)
                    SectionHeader("Live conversation")
                    Spacer()
                    Text("\(Demo.conversation.count) messages").font(BrandFont.sans(11)).foregroundStyle(Color.inkTertiary)
                }
                ForEach(recent) { m in
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(speaker(m)).font(BrandFont.sansBold(11)).tracking(0.4)
                            .foregroundStyle(m.role == .advisor ? Color.allworthAccent : Color.inkTertiary)
                        Text(m.text).font(BrandFont.sans(14)).foregroundStyle(Color.inkSecondary).lineLimit(1)
                    }
                }
                HStack(spacing: 8) {
                    Spacer()
                    Text("Open conversation").font(BrandFont.sansBold(14)).foregroundStyle(Color.allworthAccent)
                    Image(systemName: "arrow.right").font(.system(size: 15, weight: .semibold)).foregroundStyle(Color.allworthAccent)
                    Spacer()
                }
                .padding(.top, 2)
            }
            .padding(16).card()
        }
        .buttonStyle(.plain)
    }

    private func speaker(_ m: Demo.ConvMsg) -> String {
        switch m.role {
        case .advisor: return (m.advisorName ?? "You").split(separator: " ").first.map(String.init)?.uppercased() ?? "YOU"
        case .user: return clientName.uppercased()
        case .assistant: return "ASSISTANT"
        }
    }
}

// MARK: - Client conversation (transcript + interject)

private struct ClientConversationView: View {
    let convo: Demo.ConvRef
    @State private var messages = Demo.conversation
    @State private var draft = ""

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(spacing: 12) {
                    ForEach(messages) { m in TranscriptBubble(m: m, clientName: convo.clientName) }
                }
                .padding(20)
            }
            composer
        }
        .background(Color.surfacePrimary.ignoresSafeArea())
        .navigationTitle("\(convo.clientName)'s conversation")
        .navigationBarTitleDisplayMode(.inline)
    }

    private var composer: some View {
        VStack(spacing: 4) {
            HStack(alignment: .bottom, spacing: 8) {
                TextField("Message \(convo.clientName) in this thread…", text: $draft, axis: .vertical)
                    .font(BrandFont.sans(15)).foregroundStyle(Color.inkPrimary)
                    .padding(.horizontal, 16).padding(.vertical, 10)
                    .background(Capsule().fill(Color.white).overlay(Capsule().stroke(Color.hairline, lineWidth: 1)))
                Button {
                    let body = draft.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !body.isEmpty else { return }
                    messages.append(Demo.ConvMsg(role: .advisor, text: body, advisorName: Demo.advisorName))
                    draft = ""
                } label: {
                    Image(systemName: "arrow.up").font(.system(size: 18, weight: .semibold)).foregroundStyle(.white)
                        .frame(width: 38, height: 38).background(Circle().fill(Color.allworthNavy))
                }
                .opacity(draft.trimmingCharacters(in: .whitespaces).isEmpty ? 0.35 : 1)
            }
            Text("Posts as you into \(convo.clientName)'s thread — the assistant treats it as advisor context.")
                .font(BrandFont.sans(11)).foregroundStyle(Color.inkTertiary)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 12)
        .background(Color.surfacePrimary)
        .overlay(alignment: .top) { Rectangle().fill(Color.hairline).frame(height: 1) }
    }
}

private struct TranscriptBubble: View {
    let m: Demo.ConvMsg
    let clientName: String

    var body: some View {
        switch m.role {
        case .advisor:
            VStack(alignment: .trailing, spacing: 3) {
                Text(m.text).font(BrandFont.sans(15)).foregroundStyle(.white).lineSpacing(6)
                    .padding(.horizontal, 16).padding(.vertical, 12)
                    .background(UnevenRoundedRectangle(topLeadingRadius: 16, bottomLeadingRadius: 16, bottomTrailingRadius: 6, topTrailingRadius: 16).fill(Color.allworthNavy))
                    .frame(maxWidth: 300, alignment: .trailing)
                Text("\((m.advisorName ?? "You").split(separator: " ").first.map(String.init) ?? "You") · you")
                    .font(BrandFont.sans(11)).foregroundStyle(Color.inkTertiary)
            }
            .frame(maxWidth: .infinity, alignment: .trailing)
        case .user:
            HStack(alignment: .bottom, spacing: 8) {
                ZStack {
                    Circle().fill(Color.inkFaint).frame(width: 28, height: 28)
                    Text(String(clientName.prefix(1)).uppercased()).font(BrandFont.sansBold(12)).foregroundStyle(Color.inkSecondary)
                }
                .padding(.bottom, 18)
                VStack(alignment: .leading, spacing: 3) {
                    Text(m.text).font(BrandFont.sans(15)).foregroundStyle(Color.inkPrimary).lineSpacing(6)
                        .padding(.horizontal, 16).padding(.vertical, 12)
                        .background(UnevenRoundedRectangle(topLeadingRadius: 16, bottomLeadingRadius: 6, bottomTrailingRadius: 16, topTrailingRadius: 16).fill(Color.white)
                            .overlay(UnevenRoundedRectangle(topLeadingRadius: 16, bottomLeadingRadius: 6, bottomTrailingRadius: 16, topTrailingRadius: 16).stroke(Color.hairline, lineWidth: 1)))
                    Text(clientName).font(BrandFont.sans(11)).foregroundStyle(Color.inkTertiary).padding(.leading, 4)
                }
                Spacer(minLength: 0)
            }
        case .assistant:
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 4) {
                    Image(systemName: "sparkles").font(.system(size: 11)).foregroundStyle(Color.inkTertiary)
                    Text("ASSISTANT").font(BrandFont.sansBold(10)).tracking(0.5).foregroundStyle(Color.inkTertiary)
                }
                Text(m.text).font(BrandFont.sans(13)).foregroundStyle(Color.inkSecondary).lineSpacing(6).lineLimit(6)
            }
            .padding(.leading, 12)
            .overlay(alignment: .leading) { Rectangle().fill(Color.inkFaint).frame(width: 2) }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}
