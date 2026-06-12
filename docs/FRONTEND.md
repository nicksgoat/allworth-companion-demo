# Frontend

## Stack

- Expo SDK 52
- React Native 0.76
- React 18
- TypeScript
- Ionicons through `@expo/vector-icons`
- React Native Web for browser testing

## Entry Points

- [apps/mobile/index.js](/home/stevenluong/MobileApp/apps/mobile/index.js) registers the Expo root component.
- [apps/mobile/App.tsx](/home/stevenluong/MobileApp/apps/mobile/App.tsx) contains the current app shell, screens, state, and styles.

The entrypoint imports `./App.tsx` explicitly because the workspace setup can otherwise make Metro resolve `expo/AppEntry.js` from the wrong location.

## Current Screens

### Chat

The chat screen is the default experience. It includes:

- App header and profile shortcut.
- Total invested assets panel.
- Priority concentration insight.
- Suggested prompt cards.
- Chat message thread.
- Structured result cards returned from the backend.
- Fixed composer.

### Goals

The goals screen includes:

- Retirement readiness summary.
- Progress cards for multiple goals.
- Editable household assumptions.

### Portfolio

The portfolio screen includes:

- Total portfolio value.
- Holding allocation rows.
- Progress bars for allocation weights.
- Recommendation cards.

### Advisor

The advisor screen includes:

- Advisor profile.
- Message and schedule actions.
- Advisor brief cards.

## Local State

Current state lives in `App.tsx`:

- Selected tab.
- Household assumptions.
- Demo portfolio.
- Chat messages.
- Draft message.
- Latest backend response.
- Loading and error states.

This is acceptable for the prototype. Production should split state by feature and move durable session state to an authenticated backend.

## API Client

[apps/mobile/src/api.ts](/home/stevenluong/MobileApp/apps/mobile/src/api.ts) owns:

- API base URL selection.
- Chat request.
- Portfolio review request.
- TypeScript types matching backend response models.

Default API URL:

```text
http://127.0.0.1:8000
```

For a physical mobile device, set:

```bash
export EXPO_PUBLIC_API_URL="http://YOUR_LAN_IP:8000"
```

## Styling Direction

The current visual direction is a mobile wealth app:

- Off-white background.
- Deep green primary brand color.
- White cards with subtle borders.
- Compact 8px radius.
- Bottom navigation.
- Dense but readable financial cards.
- Progress bars for goals and allocation.

## Refactor Plan

Split [App.tsx](/home/stevenluong/MobileApp/apps/mobile/App.tsx) into:

```text
apps/mobile/src/screens/ChatScreen.tsx
apps/mobile/src/screens/GoalsScreen.tsx
apps/mobile/src/screens/PortfolioScreen.tsx
apps/mobile/src/screens/AdvisorScreen.tsx
apps/mobile/src/components/AppHeader.tsx
apps/mobile/src/components/BottomTabs.tsx
apps/mobile/src/components/Progress.tsx
apps/mobile/src/components/ActionCard.tsx
apps/mobile/src/components/MessageBubble.tsx
apps/mobile/src/theme.ts
```

Recommended order:

1. Extract presentational components.
2. Extract screens.
3. Move demo constants into fixtures.
4. Add a small app state hook.
5. Add screen-level tests.

## Expected Frontend Enhancements

- Render `suggested_prompts` from the backend.
- Add conversation reset.
- Add advisor brief save/share affordance.
- Add empty states for each tab.
- Add account grouping on Portfolio.
- Add source/assumption disclosure in chat answers.
- Add accessibility labels for buttons and tab navigation.
