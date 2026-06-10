import SwiftUI

struct ToolChipRow: View {
    let chips: [ToolChip]
    let sources: [String]
    let collapsed: Bool

    var body: some View {
        if collapsed && !sources.isEmpty {
            HStack(spacing: 6) {
                Image(systemName: "text.magnifyingglass")
                    .font(.system(size: 12))
                Text("Sources: " + sources.joined(separator: " · "))
                    .font(Theme.caption)
            }
            .foregroundStyle(Theme.inkTertiary)
            .transition(.opacity)
        } else if !collapsed && !chips.isEmpty {
            FlowLayout(spacing: 8) {
                ForEach(chips) { chip in
                    HStack(spacing: 6) {
                        if chip.running {
                            ProgressView().controlSize(.mini)
                        } else {
                            Image(systemName: "checkmark")
                                .font(.system(size: 10, weight: .semibold))
                                .foregroundStyle(Theme.allworthAccent)
                        }
                        Text(chip.label)
                            .font(Theme.caption)
                            .foregroundStyle(Theme.inkSecondary)
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(Theme.inkPrimary.opacity(0.05), in: Capsule())
                    .transition(.asymmetric(
                        insertion: .move(edge: .bottom).combined(with: .opacity),
                        removal: .opacity))
                }
            }
        }
    }
}

struct ChatMessageView: View {
    let message: ChatMessage

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if message.role == .user {
                HStack {
                    Spacer(minLength: 48)
                    Text(message.text)
                        .font(Theme.body)
                        .foregroundStyle(Theme.inkPrimary)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 10)
                        .background(Theme.inkPrimary.opacity(0.05),
                                    in: .rect(cornerRadius: 16, style: .continuous))
                }
            } else {
                ToolChipRow(chips: message.chips,
                            sources: message.sources,
                            collapsed: !message.isStreaming)
                if !message.text.isEmpty {
                    (assistantText + (message.isStreaming ? Text(" ▍").foregroundStyle(Theme.inkTertiary) : Text("")))
                        .font(Theme.body)
                        .lineSpacing(5)
                        .foregroundStyle(Theme.inkPrimary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                if !message.isStreaming && !message.sources.isEmpty {
                    AdvisorHandoffCard()
                        .padding(.top, 4)
                        .transition(.opacity)
                }
            }
        }
        .animation(Theme.spring, value: message.chips)
        .animation(Theme.spring, value: message.isStreaming)
    }

    private var assistantText: Text {
        if let attributed = try? AttributedString(
            markdown: message.text,
            options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)) {
            Text(attributed)
        } else {
            Text(message.text)
        }
    }
}

/// Minimal wrapping layout for tool chips.
struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        arrange(proposal: proposal, subviews: subviews).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let positions = arrange(proposal: proposal, subviews: subviews).positions
        for (subview, position) in zip(subviews, positions) {
            subview.place(at: CGPoint(x: bounds.minX + position.x, y: bounds.minY + position.y),
                          proposal: .unspecified)
        }
    }

    private func arrange(proposal: ProposedViewSize, subviews: Subviews) -> (size: CGSize, positions: [CGPoint]) {
        let maxWidth = proposal.width ?? .infinity
        var positions: [CGPoint] = []
        var x: CGFloat = 0, y: CGFloat = 0, rowHeight: CGFloat = 0, width: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x > 0 && x + size.width > maxWidth {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            positions.append(CGPoint(x: x, y: y))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
            width = max(width, x - spacing)
        }
        return (CGSize(width: width, height: y + rowHeight), positions)
    }
}
