import Foundation
import Observation

@Observable
final class AppState {
    let api = APIClient()

    var clientId = "maya"
    var session = "wednesday" {
        didSet { chatMessages = [] }
    }
    var mode: Mode = .client
    var showDemoControls = false
    var selectedTab: ClientTab = .home
    var chatPrefill: String?

    enum ClientTab: Hashable { case home, chat, profile }
    var backendHost = "localhost" {
        didSet {
            let host = backendHost
            Task { await api.setBaseURL(URL(string: "http://\(host):3000")!) }
        }
    }

    var dashboard: Dashboard?
    var dashboardError: String?
    var chatMessages: [ChatMessage] = []

    enum Mode: String, CaseIterable {
        case client = "Client"
        case advisor = "Advisor"
        case vision = "Vision"
    }

    init() {
        // Launch-screen overrides for automated demo verification:
        //   SIMCTL_CHILD_DEMO_SCREEN={chat|profile|advisor|vision}
        switch ProcessInfo.processInfo.environment["DEMO_SCREEN"] {
        case "chat": selectedTab = .chat
        case "profile": selectedTab = .profile
        case "advisor", "advisor_detail": mode = .advisor
        case "vision": mode = .vision
        case "controls": showDemoControls = true
        default: break
        }
    }

    func loadDashboard() async {
        do {
            dashboard = try await api.dashboard(clientId: clientId)
            dashboardError = nil
        } catch {
            dashboardError = "Can't reach the backend at http://\(backendHost):3000 — run ./run.sh first."
        }
    }

    func resetDemo() async {
        try? await api.resetDemo(clientId: clientId)
        chatMessages = []
        await loadDashboard()
    }
}
