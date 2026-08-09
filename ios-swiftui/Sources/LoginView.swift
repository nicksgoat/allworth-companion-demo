import SwiftUI

// The front door — 1:1 port of LoginScreen: the brand's Night Blue → Indigo hero
// with a soft cerulean glow, the horizontal lockup + promise, and a passwordless
// email sign-in that authenticates against the backend (POST /auth/login/email).
struct LoginView: View {
    @Environment(AppModel.self) private var app
    @Environment(LiveStore.self) private var live
    @State private var email = "nicole@demo.com"   // demo persona — one-tap Continue
    @State private var error: String?
    @State private var busy = false

    var body: some View {
        GeometryReader { proxy in
            let safeTop = proxy.safeAreaInsets.top
            ZStack {
                background
                VStack(spacing: 0) {
                    VStack(spacing: 18) {
                        AllworthWordmark(light: true)
                        Text("You get a financial ally for life.")
                            .font(BrandFont.displayItalic(17)).foregroundStyle(.white.opacity(0.82))
                            .multilineTextAlignment(.center)
                    }
                    .padding(.top, safeTop + 96)

                    VStack(alignment: .leading, spacing: 0) {
                        Text("Welcome back").font(BrandFont.displayMedium(26)).foregroundStyle(.white)
                        Text("Enter the email linked to your account.")
                            .font(BrandFont.sans(15)).foregroundStyle(.white.opacity(0.7))
                            .padding(.top, 6).padding(.bottom, 22)

                        HStack(spacing: 10) {
                            Image(systemName: "envelope").font(.system(size: 20)).foregroundStyle(.white.opacity(0.55))
                            ZStack(alignment: .leading) {
                                if email.isEmpty {
                                    Text("your.email@example.com").font(BrandFont.sans(16)).foregroundStyle(.white.opacity(0.45))
                                }
                                TextField("", text: $email)
                                    .font(BrandFont.sans(16)).foregroundStyle(.white).tint(.white)
                                    .textInputAutocapitalization(.never).autocorrectionDisabled()
                                    .keyboardType(.emailAddress)
                                    .onSubmit(submit)
                            }
                        }
                        .padding(.horizontal, 14).frame(height: 54)
                        .background(RoundedRectangle(cornerRadius: 12).fill(.white.opacity(0.08))
                            .overlay(RoundedRectangle(cornerRadius: 12).stroke(.white.opacity(0.2), lineWidth: 1)))

                        if let error {
                            HStack(spacing: 6) {
                                Image(systemName: "exclamationmark.circle.fill").font(.system(size: 16)).foregroundStyle(Color.loss)
                                Text(error).font(BrandFont.sans(13)).foregroundStyle(Color.loss)
                            }
                            .padding(.top, 12)
                        }

                        Button(action: submit) {
                            Text(busy ? "Signing in…" : "Continue").font(BrandFont.sansBold(16)).foregroundStyle(Color.allworthNavy)
                                .frame(maxWidth: .infinity).frame(height: 54)
                                .background(RoundedRectangle(cornerRadius: 12).fill(.white))
                                .opacity(busy ? 0.7 : 1)
                        }
                        .disabled(busy)
                        .padding(.top, 18)
                    }
                    .padding(.top, 56)

                    Spacer()
                    Text("Don't have access? Contact your financial advisor.")
                        .font(BrandFont.sans(12.5)).foregroundStyle(.white.opacity(0.55))
                        .multilineTextAlignment(.center)
                }
                .padding(.horizontal, 28)
                .padding(.bottom, 20)
            }
            .ignoresSafeArea()
        }
    }

    private var background: some View {
        ZStack {
            LinearGradient(colors: [.nightBlue, .allworthNavy], startPoint: .top, endPoint: .bottom)
            RadialGradient(colors: [Color.allworthAccent.opacity(0.32), .clear],
                           center: UnitPoint(x: 0.5, y: 0.26), startRadius: 0, endRadius: 460)
        }
    }

    private func submit() {
        let e = email.trimmingCharacters(in: .whitespaces).lowercased()
        guard e.contains("@") else { error = "Please enter a valid email address."; return }
        error = nil; busy = true
        Task {
            do {
                let res = try await APIClient.login(email: e)
                APIClient.token = res.token
                await live.load()               // refresh tabs with authed data
                busy = false
                withAnimation(.easeOut(duration: 0.3)) { app.loggedIn = true }
            } catch {
                busy = false
                self.error = "We couldn't find an account for that email."
            }
        }
    }
}
