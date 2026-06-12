#!/usr/bin/env bash
# Allworth demo — one command runs everything: FastAPI backend + the app.
#
#   ./demo.sh --web      backend + web app in your browser (http://localhost:8081) — demo target
#   ./demo.sh            backend + iOS app (Debug build, Metro attached)
#   ./demo.sh --release  backend + iOS app (Release build, no Metro)
#   ./demo.sh --android  backend + Android app (Debug build, Metro attached)
#
# Ctrl-C stops everything this script started.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$ROOT/frontend"
LOG=/tmp/allworth-backend.log

CONFIG="Debug"
# Default to web on non-Mac (Linux/Windows) since Xcode is unavailable.
if [[ "$(uname)" == "Darwin" ]]; then
  PLATFORM="ios"
else
  PLATFORM="web"
fi
for arg in "$@"; do
  case "$arg" in
    --release) CONFIG="Release" ;;
    --android) PLATFORM="android" ;;
    --web) PLATFORM="web" ;;
    *) echo "Unknown option: $arg (use --web, --android, and/or --release)"; exit 1 ;;
  esac
done

command -v uv >/dev/null 2>&1 || { echo "ERROR: uv is required — install: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "ERROR: node/npm is required — https://nodejs.org"; exit 1; }

if [ "$PLATFORM" = "ios" ]; then
  command -v xcrun >/dev/null 2>&1 || { echo "ERROR: Xcode is required for iOS (Mac App Store); open it once so it installs its components. On a non-Mac, use ./demo.sh --web"; exit 1; }
elif [ "$PLATFORM" = "web" ]; then
  if [ "$CONFIG" = "Release" ]; then
    echo "NOTE: --release is iOS-only. The web app runs the Expo dev server."
    CONFIG="Debug"
  fi
elif [ "$PLATFORM" = "android" ]; then
  export ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
  export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$PATH"
  if [ -z "${JAVA_HOME:-}" ] && [ -d /opt/homebrew/opt/openjdk@17 ]; then
    export JAVA_HOME=/opt/homebrew/opt/openjdk@17
  fi
  command -v adb >/dev/null 2>&1 || { echo "ERROR: Android SDK not found (looked in \$ANDROID_HOME=$ANDROID_HOME). Install Android Studio or: brew install openjdk@17 && brew install --cask android-commandlinetools, then sdkmanager platform-tools emulator + a system image."; exit 1; }
  if [ "$CONFIG" = "Release" ]; then
    echo "NOTE: --release is iOS-only (Android release builds block plain-HTTP to the backend). Building Android Debug."
    CONFIG="Debug"
  fi
fi

BACKEND_PID=""
EMULATOR_PID=""
cleanup() {
  if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo
    echo "Stopping backend (pid $BACKEND_PID)"
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [ -n "$EMULATOR_PID" ] && kill -0 "$EMULATOR_PID" 2>/dev/null; then
    echo "Stopping Android emulator (pid $EMULATOR_PID)"
    kill "$EMULATOR_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# 1. Backend on :3000 (reuse a healthy one if it's already up).
if curl -sf -m 1 http://localhost:3000/api/health >/dev/null 2>&1; then
  echo "Backend already running on :3000 — reusing it."
else
  echo "Starting backend (log: $LOG)…"
  "$ROOT/run.sh" >"$LOG" 2>&1 &
  BACKEND_PID=$!
  for _ in $(seq 1 30); do
    curl -sf -m 1 http://localhost:3000/api/health >/dev/null 2>&1 && break
    sleep 1
  done
  curl -sf -m 1 http://localhost:3000/api/health >/dev/null 2>&1 || { echo "ERROR: backend failed to start — see $LOG"; exit 1; }
  echo "Backend up: http://localhost:3000"
fi

# 2. The app.
cd "$APP_DIR"
if [ ! -d node_modules ]; then
  echo "Installing app dependencies…"
  npm install --no-audit --no-fund
fi

if [ "$PLATFORM" = "web" ]; then
  echo "Starting the web app — your browser will open http://localhost:8081…"
  npx expo start --web --port 8081   # stays attached; Ctrl-C stops it, then the backend
elif [ "$PLATFORM" = "android" ]; then
  # Boot an emulator if no device/emulator is connected.
  if ! adb devices | awk 'NR>1 && $2=="device"' | grep -q .; then
    AVD="$(emulator -list-avds 2>/dev/null | head -1)"
    [ -n "$AVD" ] || { echo "ERROR: no Android Virtual Device found — create one in Android Studio (Device Manager) or with avdmanager."; exit 1; }
    echo "Booting Android emulator: $AVD…"
    emulator -avd "$AVD" -no-snapshot-save >/dev/null 2>&1 &
    EMULATOR_PID=$!
    adb wait-for-device
    until [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; do sleep 2; done
    echo "Emulator booted."
  fi
  echo "Building and launching the Android app (Debug)…"
  # The app reaches the Mac's backend via 10.0.2.2 automatically on Android.
  npx expo run:android   # stays attached to Metro; Ctrl-C stops Metro, then the rest
else
  echo "Building and launching the iOS app ($CONFIG)…"
  if [ "$CONFIG" = "Release" ]; then
    npx expo run:ios --configuration Release --no-bundler
    echo
    if [ -n "$BACKEND_PID" ]; then
      echo "App launched (Release — no Metro). Backend is running; Ctrl-C here stops it."
      wait "$BACKEND_PID"
    else
      echo "App launched (Release — no Metro). Backend was already running — leaving it up."
    fi
  else
    # Debug stays attached to Metro; Ctrl-C stops Metro, then the backend.
    npx expo run:ios
  fi
fi
