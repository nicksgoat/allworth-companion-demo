import SwiftUI

// SwiftUI copy of the Allworth companion app. Design system, navy heroes, the
// glass header, and the Home logo "hello" + scroll handoff are ported from the
// React Native app (../frontend). Fonts (Playfair Display + Lato) are bundled
// and registered via UIAppFonts in Info.plist.
@main
struct AllworthApp: App {
    @State private var app = AppModel()
    @State private var live = LiveStore()
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
            .task { await live.load() }
            .onAppear {
                // Screenshot hook: jump straight to the app past the login gate.
                if ProcessInfo.processInfo.environment["SKIP_LOGIN"] == "1" { app.loggedIn = true }
            }
        }
    }
}
