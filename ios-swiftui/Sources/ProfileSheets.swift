import SwiftUI

// Profile's tapped-in sheets, ported 1:1 from screens/{FactDetailSheet,
// MeetingNoteDetailSheet, DocumentsSheet, GoalsSheet, AdvisorConciergeSheet}.

// MARK: - Fact detail (governed memory)

struct FactDetailSheet: View {
    let fact: Demo.LearnedFact
    let categoryLabel: String
    let onClose: () -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                VStack(alignment: .leading, spacing: 6) {
                    SheetHeaderView(title: categoryLabel, onClose: onClose)
                    Text(fact.fact).font(BrandFont.displayMedium(22)).foregroundStyle(Color.inkPrimary).lineSpacing(7)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                VStack(alignment: .leading, spacing: 12) {
                    SectionHeader("Why do I know this")
                    HStack(alignment: .top, spacing: 10) {
                        RoundedRectangle(cornerRadius: 2).fill(Color.allworthAccent).frame(width: 3)
                        Text("“\(fact.quote)”").font(BrandFont.sansItalic(15)).foregroundStyle(Color.inkSecondary).lineSpacing(6)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .fixedSize(horizontal: false, vertical: true)
                    prov("bubble.left", "Source", "Your conversation")
                    prov("clock", "Learned", fact.learned)
                    prov("chart.bar.xaxis", "Confidence", "\(fact.confidence)%")
                    prov("checkmark.shield", "Status", "Active")
                }

                HStack(alignment: .top, spacing: 10) {
                    Image(systemName: "lock").font(.system(size: 18)).foregroundStyle(Color.allworthNavy)
                    Text("You're in control. Facts are never shared without your consent, and anything you remove stays removed — the removal itself is logged for compliance.")
                        .font(BrandFont.sans(13)).foregroundStyle(Color.inkSecondary).lineSpacing(6)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .padding(14).background(RoundedRectangle(cornerRadius: 12).fill(Color.inkFaint))

                HStack(spacing: 8) {
                    Image(systemName: "trash").font(.system(size: 18)).foregroundStyle(Color.loss)
                    Text("Forget this detail").font(BrandFont.sansBold(17)).foregroundStyle(Color.loss)
                }
                .frame(maxWidth: .infinity).padding(.vertical, 14)
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.loss, lineWidth: 1))

                DisclaimerFooter()
            }
            .padding(20)
        }
        .background(Color.surfacePrimary.ignoresSafeArea())
    }

    private func prov(_ icon: String, _ label: String, _ value: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: icon).font(.system(size: 15)).foregroundStyle(Color.inkTertiary).frame(width: 18)
            Text(label).font(BrandFont.sans(14)).foregroundStyle(Color.inkTertiary).frame(width: 86, alignment: .leading)
            Text(value).font(BrandFont.sansBold(14)).foregroundStyle(Color.inkPrimary)
            Spacer(minLength: 0)
        }
    }
}

// MARK: - Meeting note detail

struct MeetingNoteDetailSheet: View {
    let note: Demo.MeetingNote
    let onClose: () -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                VStack(alignment: .leading, spacing: 8) {
                    SheetHeaderView(title: "Meeting note", onClose: onClose)
                    Text(note.title).font(BrandFont.displayMedium(24)).foregroundStyle(Color.allworthNavy).lineSpacing(6)
                    Text("\(note.date) · with \(note.advisor)").font(BrandFont.sans(14)).foregroundStyle(Color.inkTertiary)
                }
                Text(note.summary).font(BrandFont.sans(17)).foregroundStyle(Color.inkPrimary).lineSpacing(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                VStack(alignment: .leading, spacing: 12) {
                    SectionHeader("Who was there")
                    ForEach(note.attendees, id: \.self) { person in
                        HStack(spacing: 10) {
                            Image(systemName: "person.crop.circle").font(.system(size: 20)).foregroundStyle(Color.inkTertiary)
                            Text(person).font(BrandFont.sans(16)).foregroundStyle(Color.inkPrimary)
                        }
                    }
                }
                DisclaimerFooter()
            }
            .padding(20)
        }
        .background(Color.surfacePrimary.ignoresSafeArea())
    }
}

// MARK: - Documents (vault)

struct DocumentsSheet: View {
    let onClose: () -> Void
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    Text("Documents").font(BrandFont.displayMedium(26)).foregroundStyle(Color.allworthNavy)
                    Spacer()
                    closeChip(onClose)
                }
                VStack(spacing: 8) {
                    SectionHeader("Your vault")
                    ForEach(Demo.documents) { doc in
                        HStack(spacing: 12) {
                            ZStack {
                                RoundedRectangle(cornerRadius: 10).fill(Color.ice).frame(width: 36, height: 36)
                                Image(systemName: doc.icon).font(.system(size: 18)).foregroundStyle(Color.allworthNavy)
                            }
                            VStack(alignment: .leading, spacing: 2) {
                                Text(doc.name).font(BrandFont.sansBold(15)).foregroundStyle(Color.inkPrimary)
                                Text(doc.meta).font(BrandFont.sans(12)).foregroundStyle(Color.inkTertiary)
                            }
                            Spacer(minLength: 8)
                            Image(systemName: "chevron.right").font(.system(size: 15, weight: .semibold)).foregroundStyle(Color.inkTertiary)
                        }
                        .padding(.horizontal, 16).padding(.vertical, 12)
                        .card()
                    }
                }
                Text("Vault synced with your advisor's records. Ask in chat about any document — the assistant knows what's here.")
                    .font(BrandFont.sans(14)).foregroundStyle(Color.inkSecondary).lineSpacing(6)
                DisclaimerFooter()
            }
            .padding(20)
        }
        .background(Color.surfacePrimary.ignoresSafeArea())
    }
}

// MARK: - Goals

struct GoalsSheet: View {
    let onClose: () -> Void
    @State private var expanded: Set<String> = []
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack(alignment: .top, spacing: 12) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("My goals").font(BrandFont.displayMedium(26)).foregroundStyle(Color.allworthNavy)
                        Text(Demo.goalsSummary).font(BrandFont.sans(14)).foregroundStyle(Color.inkSecondary)
                    }
                    Spacer()
                    closeChip(onClose)
                }

                ForEach(Demo.goals) { g in
                    VStack(alignment: .leading, spacing: 12) {
                        goalHeader(g)
                            .contentShape(Rectangle())
                            .onTapGesture {
                                guard !g.income else { return }
                                withAnimation(.easeInOut(duration: 0.22)) {
                                    if expanded.contains(g.id) { expanded.remove(g.id) } else { expanded.insert(g.id) }
                                }
                            }
                        if g.income {
                            Text(g.plan).font(BrandFont.sans(14)).foregroundStyle(Color.inkSecondary).lineSpacing(4)
                        } else {
                            GeometryReader { geo in
                                ZStack(alignment: .leading) {
                                    Capsule().fill(Color.inkFaint)
                                    Capsule().fill(g.onTrack ? Color.chartEvergreen : Color.attention)
                                        .frame(width: geo.size.width * CGFloat(min(100, g.fundedPct)) / 100)
                                }
                            }
                            .frame(height: 8)
                            Text("\(usd(g.currentFunded)) of \(usd(g.target)) · \(g.plan)")
                                .font(BrandFont.sans(14)).foregroundStyle(Color.inkSecondary).monospacedDigit()
                            if expanded.contains(g.id) { goalDetail(g) }
                        }
                    }
                    .padding(16).card()
                }

                SectionHeader("How this works")
                Text("These are the goals in your Allworth plan. Adjust a plan and save it — your assistant uses it when you talk about goals, and your advisor sees it too. Decisions stay with you and your advisor.")
                    .font(BrandFont.sans(14)).foregroundStyle(Color.inkSecondary).lineSpacing(5)
                DisclaimerFooter()
            }
            .padding(20)
        }
        .background(Color.surfacePrimary.ignoresSafeArea())
    }

    private func goalHeader(_ g: Demo.Goal) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "flag").font(.system(size: 15)).foregroundStyle(Color.allworthAccent)
            Text(g.label).font(BrandFont.sansBold(16)).foregroundStyle(Color.inkPrimary).lineLimit(1)
            Spacer(minLength: 6)
            Text(g.onTrack ? "On track" : "Needs attention")
                .font(BrandFont.sansBold(12)).foregroundStyle(g.onTrack ? Color.gain : Color.attention)
            if !g.income {
                Image(systemName: "chevron.down").font(.system(size: 13, weight: .semibold)).foregroundStyle(Color.inkTertiary)
                    .rotationEffect(.degrees(expanded.contains(g.id) ? 180 : 0))
            }
        }
    }

    // Funding breakdown revealed when a lump-sum goal is tapped open.
    private func goalDetail(_ g: Demo.Goal) -> some View {
        let remaining = max(0, g.target - g.currentFunded)
        return VStack(spacing: 0) {
            Hairline().padding(.vertical, 4)
            detailRow("Target", usd(g.target))
            detailRow("Funded so far", "\(usd(g.currentFunded)) · \(g.fundedPct)%")
            detailRow("Still to fund", usd(remaining))
            detailRow("Status", g.onTrack ? "On track" : "Needs attention",
                      color: g.onTrack ? .gain : .attention)
        }
    }

    private func detailRow(_ label: String, _ value: String, color: Color = .inkPrimary) -> some View {
        HStack {
            Text(label).font(BrandFont.sans(14)).foregroundStyle(Color.inkTertiary)
            Spacer()
            Text(value).font(BrandFont.sansBold(14)).foregroundStyle(color).monospacedDigit()
        }
        .padding(.vertical, 7)
    }
}

// MARK: - Advisor concierge (book / request a topic)

struct AdvisorConciergeSheet: View {
    let onClose: () -> Void
    @State private var dayIdx = 0
    @State private var slot: String?
    @State private var topic = ""
    @State private var booked: String?
    @State private var requested = false

    private var days: [Demo.AvailDay] { Demo.availability }
    private var day: Demo.AvailDay { days[min(dayIdx, days.count - 1)] }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                HStack(spacing: 12) {
                    ZStack {
                        Circle().fill(Color.allworthNavy).frame(width: 44, height: 44)
                        Text(Demo.advisorInitials).font(BrandFont.sansBold(15)).foregroundStyle(.white)
                    }
                    VStack(alignment: .leading, spacing: 2) {
                        Text(Demo.advisorName).font(BrandFont.sansBold(18)).foregroundStyle(Color.inkPrimary)
                        Text(Demo.advisorTitle).font(BrandFont.sans(13)).foregroundStyle(Color.inkSecondary)
                    }
                    Spacer()
                    closeChip(onClose)
                }

                VStack(alignment: .leading, spacing: 12) {
                    SectionHeader("Book a meeting")
                    if let booked {
                        confirmCard {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("You're on \(Demo.advisorFirst)'s calendar for \(booked).")
                                    .font(BrandFont.sans(15)).foregroundStyle(Color.inkPrimary).lineSpacing(5)
                                Text("Pick a different time").font(BrandFont.sansBold(13)).foregroundStyle(Color.allworthAccent)
                                    .onTapGesture { self.booked = nil }
                            }
                        }
                    } else {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 8) {
                                ForEach(Array(days.enumerated()), id: \.element.id) { i, d in
                                    let active = i == dayIdx
                                    VStack(spacing: 2) {
                                        Text(d.dow).font(BrandFont.sans(12)).foregroundStyle(active ? .white : Color.inkTertiary)
                                        Text(d.dayNum).font(BrandFont.sansBold(16)).foregroundStyle(active ? .white : Color.inkPrimary)
                                    }
                                    .frame(minWidth: 58).padding(.horizontal, 16).padding(.vertical, 8)
                                    .background(RoundedRectangle(cornerRadius: Radius.chip).fill(active ? Color.allworthNavy : Color.white))
                                    .overlay(RoundedRectangle(cornerRadius: Radius.chip).stroke(Color.allworthNavy.opacity(active ? 0 : 0.05), lineWidth: 1))
                                    .onTapGesture { dayIdx = i; slot = nil }
                                }
                            }
                        }
                        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                            ForEach(day.slots, id: \.self) { s in
                                let active = slot == s
                                Text(s)
                                    .font(BrandFont.sansBold(14)).foregroundStyle(active ? Color.allworthAccent : Color.inkPrimary).monospacedDigit()
                                    .frame(maxWidth: .infinity).padding(.vertical, 12)
                                    .background(RoundedRectangle(cornerRadius: Radius.chip).fill(active ? Color.allworthAccent.opacity(0.08) : Color.white))
                                    .overlay(RoundedRectangle(cornerRadius: Radius.chip).stroke(active ? Color.allworthAccent : Color.allworthNavy.opacity(0.05), lineWidth: 1))
                                    .onTapGesture { slot = s }
                            }
                        }
                        Text(slot != nil ? "Confirm \(day.long) · \(slot!)" : "Pick a time")
                            .font(BrandFont.sansBold(15)).foregroundStyle(.white)
                            .frame(maxWidth: .infinity).padding(.vertical, 12)
                            .background(RoundedRectangle(cornerRadius: Radius.chip).fill(Color.allworthNavy))
                            .opacity(slot == nil ? 0.4 : 1)
                            .onTapGesture { if let slot { booked = "\(day.long) · \(slot)" } }
                    }
                }

                VStack(alignment: .leading, spacing: 12) {
                    SectionHeader("Request a topic")
                    if requested {
                        confirmCard {
                            Text("Sent. \(Demo.advisorFirst) will come prepared to your next conversation.")
                                .font(BrandFont.sans(15)).foregroundStyle(Color.inkPrimary).lineSpacing(5)
                        }
                    } else {
                        ZStack(alignment: .topLeading) {
                            RoundedRectangle(cornerRadius: Radius.card).fill(Color.white)
                                .overlay(RoundedRectangle(cornerRadius: Radius.card).stroke(Color.allworthNavy.opacity(0.05), lineWidth: 1))
                            if topic.isEmpty {
                                Text("What should \(Demo.advisorFirst) look into?")
                                    .font(BrandFont.sans(16)).foregroundStyle(Color.inkTertiary).padding(16)
                            }
                            TextField("", text: $topic, axis: .vertical)
                                .font(BrandFont.sans(16)).foregroundStyle(Color.inkPrimary).padding(16)
                        }
                        .frame(minHeight: 84)
                        Text("Send to \(Demo.advisorFirst)")
                            .font(BrandFont.sansBold(15)).foregroundStyle(.white)
                            .frame(maxWidth: .infinity).padding(.vertical, 12)
                            .background(RoundedRectangle(cornerRadius: Radius.chip).fill(Color.allworthNavy))
                            .opacity(topic.trimmingCharacters(in: .whitespaces).isEmpty ? 0.4 : 1)
                            .onTapGesture { if !topic.trimmingCharacters(in: .whitespaces).isEmpty { requested = true } }
                    }
                }

                DisclaimerFooter()
            }
            .padding(20)
        }
        .background(Color.surfacePrimary.ignoresSafeArea())
    }

    private func confirmCard<C: View>(@ViewBuilder _ content: () -> C) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "checkmark.circle.fill").font(.system(size: 22)).foregroundStyle(Color.gain)
            content()
            Spacer(minLength: 0)
        }
        .padding(16).card()
    }
}

// MARK: - Shared close chip

func closeChip(_ onClose: @escaping () -> Void) -> some View {
    Button(action: onClose) {
        Image(systemName: "xmark").font(.system(size: 16, weight: .medium)).foregroundStyle(Color.inkSecondary)
            .frame(width: 32, height: 32)
            .glassEffect(.regular.interactive(), in: Circle())
    }
    .buttonStyle(.plain)
}
