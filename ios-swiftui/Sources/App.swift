import SwiftUI

// SwiftUI copy of the Allworth companion app. Design system, navy heroes, the
// glass header, and the Home logo "hello" + scroll handoff are ported from the
// React Native app (../frontend). Fonts (Playfair Display + Lato) are bundled
// and registered via UIAppFonts in Info.plist.
@main
struct AllworthApp: App {
    var body: some Scene {
        WindowGroup {
            RootView()
        }
    }
}
