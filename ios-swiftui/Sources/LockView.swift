import SwiftUI

// Biometric relaunch gate — 1:1 port of LockScreen. Navy field, the Iris mark,
// a welcome, and Face ID. No real biometrics in this copy, so "Unlock" just
// dismisses; "Sign in with email instead" drops back to the login screen.
struct LockView: View {
    @Environment(AppModel.self) private var app

    var body: some View {
        VStack {
            Spacer()
            VStack(spacing: Space.s3) {
                ZStack {
                    Circle().fill(.white.opacity(0.08)).frame(width: 72, height: 72)
                    AllworthMark(color: .white, size: 34)
                }
                .padding(.bottom, Space.s2)
                Text("Welcome back, \(Demo.clientFirstName)").font(BrandFont.displayMedium(28)).foregroundStyle(.white)
                Text("Your account is locked").font(BrandFont.sans(14)).foregroundStyle(.white.opacity(0.65))
            }
            Spacer()
            VStack(spacing: Space.s4) {
                Button { withAnimation(.easeOut(duration: 0.3)) { app.locked = false } } label: {
                    HStack(spacing: Space.s2) {
                        Image(systemName: "lock.open").font(.system(size: 18)).foregroundStyle(Color.allworthNavy)
                        Text("Unlock with Face ID").font(BrandFont.sansBold(15)).foregroundStyle(Color.allworthNavy)
                    }
                    .frame(maxWidth: .infinity).padding(.vertical, Space.s3)
                    .background(Capsule().fill(.white))
                }
                .buttonStyle(.plain)
                Button {
                    APIClient.token = nil
                    app.locked = false; app.mode = .client; app.loggedIn = false
                } label: {
                    Text("Sign in with email instead").font(BrandFont.sans(13)).foregroundStyle(.white.opacity(0.7))
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, Space.s5)
            .padding(.bottom, 48)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.nightBlue.ignoresSafeArea())
    }
}
