# Shipping the SwiftUI app to TestFlight

This native SwiftUI app is configured to ship as the **next build of the existing
App Store Connect app** (`ascAppId 6779701863`, bundle id `com.allworth.companion`),
i.e. it **replaces** the React Native app on TestFlight. Existing testers get it as
their next update.

## Pre-set in the project (`project.yml`)

- **Bundle id:** `com.allworth.companion` (matches the RN app / existing ASC record)
- **Version / build:** `1.0.0 (15)` — build number **must exceed the latest build
  already on TestFlight**. RN's last was 14; if App Store Connect rejects 15 as a
  duplicate, bump `CURRENT_PROJECT_VERSION` in `project.yml` and re-run `xcodegen generate`.
- **App icon:** `Resources/Assets.xcassets/AppIcon.appiconset` (the official 1024px art)
- **Signing:** automatic, team `NAK8FFQZBA`
- **Export compliance:** `ITSAppUsesNonExemptEncryption = false` (no per-upload prompt)
- **Backend:** defaults to `https://allworth-demo-api.fly.dev` over HTTPS with real
  login — works on device, off-network.

## Two things to know before you ship

1. **Minimum iOS is 26.0** (required by the Liquid Glass APIs). Testers on iOS < 26
   cannot install this build — they'd stay on the last RN build (14). This is the
   cost of the native-glass copy.
2. It's a **native, non-Expo** build. Going forward this bundle id is served by the
   Xcode project here, not the EAS/Expo pipeline.

## Upload — easiest path (Xcode, uses your Apple account)

```bash
cd ios-swiftui && xcodegen generate && open AllworthSwiftUI.xcodeproj
```

In Xcode: sign in with the Apple ID on team `NAK8FFQZBA` (Settings ▸ Accounts) →
select **Any iOS Device (arm64)** → **Product ▸ Archive** → in the Organizer,
**Distribute App ▸ App Store Connect ▸ Upload**. Automatic signing will create the
distribution cert + provisioning profile on first run.

## Upload — command line (needs the signing cert/profile in the keychain)

```bash
cd ios-swiftui && xcodegen generate
xcodebuild -project AllworthSwiftUI.xcodeproj -scheme AllworthSwiftUI \
  -destination 'generic/platform=iOS' -archivePath build/Allworth.xcarchive \
  -allowProvisioningUpdates archive
xcodebuild -exportArchive -archivePath build/Allworth.xcarchive \
  -exportOptionsPlist ExportOptions.plist -exportPath build/export \
  -allowProvisioningUpdates
# then upload the .ipa with your App Store Connect API key:
xcrun altool --upload-app -t ios -f build/export/*.ipa \
  --apiKey <ASC_KEY_ID> --apiIssuer <ASC_ISSUER_ID>
```

The RN app's ASC API key ids live in `frontend/eas.json` (`submit.production.ios`);
the key file itself (`.p8`) is your credential — keep it out of the repo/logs.

After upload, the build appears in TestFlight after processing; assign it to your
test group as usual.
