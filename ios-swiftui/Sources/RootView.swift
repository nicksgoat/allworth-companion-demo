import SwiftUI

struct RootView: View {
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
