// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require("eslint/config");
const expoConfig = require("eslint-config-expo/flat");
const prettierConfig = require("eslint-config-prettier");

module.exports = defineConfig([
  expoConfig,
  prettierConfig,
  {
    ignores: ["dist/*", "ios/*"],
  },
  {
    rules: {
      // Demo screens intentionally seed loading/animation state at effect start.
      "react-hooks/set-state-in-effect": "off",
    },
  },
]);
