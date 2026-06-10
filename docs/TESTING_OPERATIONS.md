# Testing And Operations

## Setup

From project root:

```bash
cd /home/stevenluong/MobileApp
./scripts/setup.sh
```

This creates the Python virtual environment, installs backend requirements, and installs Node dependencies.

## Run Backend

```bash
cd /home/stevenluong/MobileApp
./scripts/dev-api.sh
```

Backend URL:

```text
http://127.0.0.1:8000
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

## Run Mobile With Expo

```bash
cd /home/stevenluong/MobileApp
./scripts/dev-mobile.sh
```

Expo will print a QR code and local URL.

## Run Web Preview

```bash
cd /home/stevenluong/MobileApp/apps/mobile
npx expo start --web --port 8082
```

Open:

```text
http://localhost:8082
```

## Physical Device Testing

Set the API URL to the machine LAN IP before starting Expo:

```bash
export EXPO_PUBLIC_API_URL="http://YOUR_LAN_IP:8000"
./scripts/dev-mobile.sh
```

Then scan the Expo QR code with Expo Go.

## Android Emulator

Requires Android SDK and `adb`.

If missing, Expo will show:

```text
Error: spawn adb ENOENT
```

Set:

```bash
export ANDROID_HOME="$HOME/Android/Sdk"
export PATH="$ANDROID_HOME/emulator:$ANDROID_HOME/platform-tools:$PATH"
```

Then verify:

```bash
adb version
```

## iOS Simulator

Requires macOS and Xcode. On Linux, use Expo Go on a physical iPhone or web preview.

## Tests

Frontend logic tests:

```bash
npm test
```

Backend tests:

```bash
PYTHONPATH=services/api .venv/bin/python -m pytest services/api/tests
```

TypeScript:

```bash
npx tsc --noEmit -p apps/mobile/tsconfig.json
```

All scripted tests:

```bash
./scripts/test.sh
```

## Current Test Coverage

- Currency formatting.
- Portfolio totals.
- Largest drift.
- Household field updates.
- API health.
- Chat intent routing.
- Portfolio tax-loss harvesting route.
- Backend validation.

## Recommended Test Additions

- Component smoke tests for each tab.
- API contract tests for every `ToolResult`.
- LLM mode tests with mocked provider.
- Safety tests for prohibited actions.
- Screenshot tests for web/mobile layouts.
- MCP connector tests with fixture responses.

## Operational Notes

- Keep demo mode working without network access to internal systems.
- Keep web preview available for quick stakeholder review.
- Do not run `npm audit fix --force` casually because it can introduce breaking dependency changes.
- Stop Metro with `Ctrl+C` when done.
- Avoid checking in generated caches or virtual environments.
