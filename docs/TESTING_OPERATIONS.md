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
http://127.0.0.1:3000
```

Health check:

```bash
curl http://127.0.0.1:3000/api/health
```

## Run Mobile With Expo

```bash
cd /home/stevenluong/MobileApp
./scripts/dev-mobile.sh
```

Expo will print a QR code and local URL.

## Run Web Preview

```bash
cd /home/stevenluong/MobileApp/frontend
EXPO_PUBLIC_API_URL=http://127.0.0.1:3000 npm run web
```

Open:

```text
http://localhost:8081
```

## Physical Device Testing

Set the API URL to the machine LAN IP before starting Expo:

```bash
export EXPO_PUBLIC_API_URL="http://YOUR_LAN_IP:3000"
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
cd backend
uv run --with pytest --with httpx python -m pytest tests
```

TypeScript:

```bash
cd frontend
npx tsc --noEmit -p tsconfig.json
```

## GPT-4o / Azure OpenAI Deployment

Keep GPT-4o credentials on the backend only. Set these as backend runtime environment variables or
deployment secrets:

```bash
LLM_PROVIDER=azure_openai
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-12-01-preview
LLM_CHAT_MODEL=gpt-4o
LLM_EXTRACT_MODEL=gpt-4o
MOBILEAPP_TOOL_MODE=demo
```

Set only the deployed backend URL in the frontend:

```bash
EXPO_PUBLIC_API_URL=https://YOUR-BACKEND-HOST
```

Never expose `AZURE_OPENAI_API_KEY` through Expo config or any `EXPO_PUBLIC_*` variable.

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
