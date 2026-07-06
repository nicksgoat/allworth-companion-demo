import SwiftUI

struct RootView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.scenePhase) private var scenePhase
    @State private var selection: Int

    init() {
        // iOS 26 renders the standard TabView as a floating Liquid Glass bar —
        // no appearance override, so the glass shows through.
        let tab = ProcessInfo.processInfo.environment["START_TAB"] ?? "home"
        _selection = State(initialValue: ["home": 0, "wealth": 1, "chat": 2, "profile": 3][tab] ?? 0)
    }

    var body: some View {
        @Bindable var app = app
        ZStack {
            switch app.mode {
            case .vision: VisionView()
            case .advisor: AdvisorRootView().transition(.opacity)
            case .client: tabs
            }
            if app.locked { LockView().transition(.opacity) }
        }
        .sheet(isPresented: $app.showDemoControls) { DemoControlView() }
        .onAppear {
            switch ProcessInfo.processInfo.environment["START_MODE"] {
            case "advisor": app.mode = .advisor
            case "vision": app.mode = .vision
            default: break
            }
            if ProcessInfo.processInfo.environment["LOCK"] == "1" { app.locked = true }
            if ProcessInfo.processInfo.environment["DEMO_CONTROLS"] == "1" { app.showDemoControls = true }
        }
        .onChange(of: scenePhase) { _, phase in
            // Fintech relaunch gate: re-lock whenever the app leaves the
            // foreground, so returning to it asks for Face ID (LockScreen.tsx).
            if phase == .background { app.locked = true }
        }
    }

    private var tabs: some View {
        TabView(selection: $selection) {
            Tab("Home", systemImage: "house", value: 0) { HomeView() }
            Tab("Wealth", systemImage: "chart.pie", value: 1) { WealthView() }
            Tab("Chat", systemImage: "bubble.left", value: 2) { ChatView() }
            Tab("Profile", systemImage: "person", value: 3) { ProfileView() }
        }
        .tint(.allworthNavy)
    }
}
