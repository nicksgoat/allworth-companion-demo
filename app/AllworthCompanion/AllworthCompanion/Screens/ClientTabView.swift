import SwiftUI

struct ClientTabView: View {
    @Environment(AppState.self) private var app

    var body: some View {
        @Bindable var app = app
        TabView(selection: $app.selectedTab) {
            DashboardView()
                .tabItem { Label("Home", systemImage: "house") }
                .tag(AppState.ClientTab.home)
            ChatView()
                .tabItem { Label("Chat", systemImage: "bubble.left.and.text.bubble.right") }
                .tag(AppState.ClientTab.chat)
            ProfileView()
                .tabItem { Label("Profile", systemImage: "person") }
                .tag(AppState.ClientTab.profile)
        }
        .sensoryFeedback(.impact(weight: .light), trigger: app.selectedTab)
    }
}

/// The Allworth wordmark — appears exactly once in the client app.
/// Triple-tap opens the hidden demo control sheet.
struct AllworthWordmark: View {
    @Environment(AppState.self) private var app
    var light = false

    var body: some View {
        Text("ALLWORTH")
            .font(.system(size: 13, weight: .bold))
            .tracking(2.5)
            .foregroundStyle(light ? .white : Theme.allworthNavy)
            .contentShape(Rectangle())
            .onTapGesture(count: 3) { app.showDemoControls = true }
    }
}
