# Allworth — SwiftUI copy

A native **SwiftUI** copy of the Allworth companion app. The design system, navy
heroes, glass header, and the Home logo **"hello" + scroll handoff** are ported
from the React Native app in [`../frontend`](../frontend). Tokens track
`frontend/src/theme.ts` (which comes from the brand deck); the two should stay in
lockstep.

This is a UI copy — **static demo data, no backend** (Maya Tran / Nicole Mayer,
the same synthetic content the RN demo shows).

## Run

Requires Xcode 16+ and [XcodeGen](https://github.com/yonaskolb/XcodeGen)
(`brew install xcodegen`). The `.xcodeproj` is generated, not committed.

```sh
xcodegen generate
open AllworthSwiftUI.xcodeproj      # ⌘R on an iOS 18+ simulator
```

Or headless:

```sh
xcodegen generate
xcodebuild -scheme AllworthSwiftUI \
  -destination 'platform=iOS Simulator,name=iPhone 16 Pro' build
```

## Layout

| Path | What |
|---|---|
| `project.yml` | XcodeGen spec — iOS 18 target, bundles the fonts via `UIAppFonts` |
| `Sources/Theme.swift` | Colors, fonts (Playfair + Lato), spacing — ported from `theme.ts` |
| `Sources/Brand.swift` | The Iris mark (drawn sunburst) + the wordmark lockup |
| `Sources/Components.swift` | `NavyGradient`, the `GlassHeader` (onHero / heroReveal), scroll tracking, card/section helpers |
| `Sources/Shared.swift` | `NavyHeroBand`, entrance motion, small shared views |
| `Sources/HomeView.swift` | Home — the logo handoff + staged "hello" + attention/quick-actions/advisor |
| `Sources/{Wealth,Chat,Profile}View.swift` | The other three tabs |
| `Resources/Fonts/` | Playfair Display + Lato (same faces as the RN app) |

## Notes / next steps

- **Scope:** scaffold + all four tabs. Home is fully built (logo handoff, staged
  entrance); Wealth / Chat / Profile are faithful but lighter. Detail sheets and
  advisor mode are not ported yet.
- **Scroll tracking** uses `onScrollGeometryChange` (iOS 18) — the older
  GeometryReader-preference pattern does **not** re-emit on scroll on the current
  simulator runtime.
- **Logo:** the Iris mark is a drawn approximation. Drop in the official vector
  logo from the Allworth marketing team before anything ships.
