import SwiftUI

struct RootView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.scenePhase) private var scenePhase
    @State private var selection: Int

    init() {
        // Match the RN tab bar: light surface, navy active tint.
        let appearance = UITabBarAppearance()
        appearance.configureWithOpaqueBackground()
        appearance.backgroundColor = UIColor(Color.surfacePrimary)
        UITabBar.appearance().standardAppearance = appearance
        UITabBar.appearance().scrollEdgeAppearance = appearance

        // Optional launch hook (used only for screenshot capture).
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
            HomeView()
                .tag(0)
                .tabItem { Label("Home", systemImage: "house") }
            WealthView()
                .tag(1)
                .tabItem { Label("Wealth", systemImage: "chart.pie") }
            ChatView()
                .tag(2)
                .tabItem { Label("Chat", systemImage: "bubble.left") }
            ProfileView()
                .tag(3)
                .tabItem { Label("Profile", systemImage: "person") }
        }
        .tint(.allworthNavy)
    }
}
