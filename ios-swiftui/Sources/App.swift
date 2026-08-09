import SwiftUI
import UIKit

// SwiftUI copy of the Allworth companion app. Design system, navy heroes, the
// glass header, and the Home logo "hello" + scroll handoff are ported from the
// React Native app (../frontend). Fonts (Playfair Display + Lato) are bundled
// and registered via UIAppFonts in Info.plist.
@main
struct AllworthApp: App {
    @State private var app = AppModel()
    @State private var live = LiveStore()

    init() {
        // No rubber-band overscroll: you can't pull the navy header down past the
        // top edge (which exposed a gray gap and read as low-quality). Global.
        UIScrollView.appearance().bounces = false
        UIScrollView.appearance().alwaysBounceVertical = false
    }
    var body: some Scene {
        WindowGroup {
            Group {
                if app.loggedIn {
                    RootView()
                } else {
                    LoginView()
                }
            }
            .environment(app)
            .environment(live)
            // The brand system is a fixed light palette (Feather-Gray surfaces,
            // white cards, navy heroes). Lock to light so native Liquid Glass
            // (header, tab bar, composer) doesn't render dark in system dark mode.
            .preferredColorScheme(.light)
            .task { await live.load() }
            .onAppear {
                // Screenshot hook: auto-login (real token) and jump past the gate.
                if ProcessInfo.processInfo.environment["SKIP_LOGIN"] == "1" {
                    Task {
                        if let r = try? await APIClient.login(email: "nicole@demo.com") {
                            APIClient.token = r.token
                            await live.load()
                        }
                        app.loggedIn = true
                    }
                }
            }
        }
    }
}
