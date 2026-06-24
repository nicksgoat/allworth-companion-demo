// One-time generator: ports the official Allworth logo from the app's source of
// truth (frontend/src/components/logoPaths.ts) into web assets. Run from launch/:
//
//   node scripts/gen-logo.js
//
// Emits public/assets/{logo.svg, logo-white.svg, favicon.svg}. Re-run if the brand
// SVG in logoPaths.ts ever changes. We never hand-redraw the logo.

"use strict";
const fs = require("fs");
const path = require("path");

const SRC = path.join(__dirname, "..", "..", "frontend", "src", "components", "logoPaths.ts");
const OUT = path.join(__dirname, "..", "public", "assets");

const text = fs.readFileSync(SRC, "utf8");

function extractArray(name) {
  // Matches:  export const NAME: string[] = [ ... ];
  const re = new RegExp("export const " + name + "[^=]*=\\s*\\[([\\s\\S]*?)\\];");
  const m = text.match(re);
  if (!m) throw new Error("Could not find " + name + " in logoPaths.ts");
  // The body is a list of quoted string literals — eval it as an array literal.
  // eslint-disable-next-line no-eval
  return eval("[" + m[1] + "]");
}

const NAVY = extractArray("NAVY_PATHS"); // wordmark
const ACCENT = extractArray("ACCENT_PATHS"); // Iris mark
const NAVY_HEX = "#173D67";
const ACCENT_HEX = "#3E71B7";

function paths(arr, fill) {
  return arr.map((d) => `<path fill="${fill}" d="${d}"/>`).join("");
}

// Full horizontal lockup (mark + wordmark).
const logoSvg =
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 414 100" role="img" aria-label="Allworth">` +
  paths(NAVY, NAVY_HEX) +
  paths(ACCENT, ACCENT_HEX) +
  `</svg>\n`;

// Reversed (all-white) lockup for dark surfaces (hero, footer).
const logoWhiteSvg =
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 414 100" role="img" aria-label="Allworth">` +
  paths(NAVY, "#FFFFFF") +
  paths(ACCENT, "#FFFFFF") +
  `</svg>\n`;

// Iris symbol only — favicon / app tab icon.
const faviconSvg =
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80" role="img" aria-label="Allworth">` +
  paths(ACCENT, ACCENT_HEX) +
  `</svg>\n`;

fs.mkdirSync(OUT, { recursive: true });
fs.writeFileSync(path.join(OUT, "logo.svg"), logoSvg);
fs.writeFileSync(path.join(OUT, "logo-white.svg"), logoWhiteSvg);
fs.writeFileSync(path.join(OUT, "favicon.svg"), faviconSvg);
console.log("Wrote logo.svg, logo-white.svg, favicon.svg to public/assets/");
