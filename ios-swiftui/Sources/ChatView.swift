import SwiftUI

// Chat — light glass header (no navy hero; a hero would eat the conversation),
// an assistant opener, suggestion chips, and the composer. Static copy.
struct ChatView: View {
    private let suggestions = [
        "How does this spending affect my plan?",
        "What are my options for NVDA?",
        "What are my options for TSLA?",
    ]

    var body: some View {
        GeometryReader { proxy in
            let safeTop = proxy.safeAreaInsets.top
            ZStack(alignment: .top) {
                Color.surfacePrimary.ignoresSafeArea()

                ScrollView(showsIndicators: false) {
                    VStack(alignment: .leading, spacing: Space.s5) {
                        HStack {
                            Rectangle().fill(Color.hairline).frame(height: 1)
                            Text("Wednesday, June 10")
                                .font(BrandFont.sansBold(12)).foregroundStyle(Color.inkTertiary).fixedSize()
                            Rectangle().fill(Color.hairline).frame(height: 1)
                        }

                        Text("Welcome back, Maya. I've refreshed your full picture — plan, portfolio, and goals. A couple of things stand out worth a closer look. Where would you like to start?")
                            .font(BrandFont.sans(19))
                            .foregroundStyle(Color.inkPrimary)
                            .lineSpacing(4)

                        HStack(spacing: Space.s4) {
                            Image(systemName: "hand.thumbsup").foregroundStyle(Color.inkTertiary)
                            Image(systemName: "hand.thumbsdown").foregroundStyle(Color.inkTertiary)
                        }
                        .font(.system(size: 18))

                        VStack(alignment: .leading, spacing: Space.s2) {
                            ForEach(suggestions, id: \.self) { s in
                                Text(s)
                                    .font(BrandFont.sans(15))
                                    .foregroundStyle(Color.inkSecondary)
                                    .padding(.horizontal, Space.s4)
                                    .padding(.vertical, Space.s3)
                                    .overlay(
                                        Capsule().stroke(Color.hairline, lineWidth: 1)
                                    )
                            }
                        }
                    }
                    .padding(.horizontal, Space.s5)
                    .padding(.top, safeTop + 48 + Space.s4)
                    .padding(.bottom, 120)
                }
                .ignoresSafeArea(edges: .top)

                GlassHeader(title: "Nicole's Assistant", safeTop: safeTop,
                            actionIconOverride: "square.and.pencil")

                // Composer pinned above the tab bar.
                VStack {
                    Spacer()
                    HStack {
                        Text("Ask Allworth…")
                            .font(BrandFont.sans(18))
                            .foregroundStyle(Color.inkTertiary)
                        Spacer()
                    }
                    .padding(.horizontal, Space.s5)
                    .padding(.vertical, Space.s4)
                    .background(Color.white)
                    .clipShape(Capsule())
                    .shadow(color: Color.nightBlue.opacity(0.06), radius: 8, y: 2)
                    .padding(.horizontal, Space.s5)
                    .padding(.bottom, Space.s2)
                }
            }
        }
    }
}

// Small convenience so Chat can pass an action icon without an onAction closure.
extension GlassHeader {
    init(title: String, safeTop: CGFloat, actionIconOverride: String) {
        self.init(title: title, scrollY: 0, onHero: false, heroReveal: false,
                  actionIcon: actionIconOverride, onAction: nil, safeTop: safeTop)
    }
}
