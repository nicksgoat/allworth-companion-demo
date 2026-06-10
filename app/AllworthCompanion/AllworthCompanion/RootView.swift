import SwiftUI

struct RootView: View {
    @Environment(AppState.self) private var app

    var body: some View {
        @Bindable var app = app
        Group {
            switch app.mode {
            case .client: ClientTabView()
            case .advisor: AdvisorView()
            case .vision: VisionView()
            }
        }
        .sheet(isPresented: $app.showDemoControls) { DemoControlSheet() }
    }
}
