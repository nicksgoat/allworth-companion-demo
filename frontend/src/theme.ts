import { Platform, TextStyle } from "react-native";

// All values from ALW001_01_Brand_Dashboard_DEC2024.pdf (the brand source of truth)
export const colors = {
  // Primary palette (p.7)
  allworthNavy: "#173D67", // Indigo Blue / PMS 295C — wordmark
  allworthAccent: "#3E71B7", // Cerulean Blue / PMS 2144C — Iris symbol

  // Neutrals (p.7) — backgrounds, text boxes, table fields
  surfacePrimary: "#F3F4F4", // Feather Gray
  surfaceCard: "#FFFFFF",
  beige: "#EBE9DD",
  linen: "#F3F2E5",
  ice: "#EDF2F7",
  surfaceHero: "#0C2E4E", // Night Blue — premium dark hero/sheet surface (brand: Night Blue → Indigo)

  // Monotone (p.7) — black + dark gray for copy and stats
  inkPrimary: "#000000",
  inkSecondary: "#595959", // Dark Gray
  inkTertiary: "#828282", // Medium Gray
  hairline: "#E6E6E6", // Pale Gray
  inkFaint: "#E6E6E6", // Pale Gray — faint fills (chips, tracks, skeletons)

  // Semantic money movement — mapped onto the secondary palette
  gain: "#436434", // Evergreen
  loss: "#D26D37", // Pumpkin
  attention: "#D26D37", // Pumpkin
  // Lightened variants legible on the navy/gradient hero surfaces
  gainOnDark: "#86C98A",
  lossOnDark: "#E89B73",

  // Secondary palette — designated for infographics/charts/accents only (p.7)
  chartNightBlue: "#0C2E4E",
  chartSky: "#289FDA",
  chartEvergreen: "#436434",
  chartGold: "#A99C6C",
  chartPumpkin: "#D26D37",
  chartLightGray: "#BEBEBE",
};

// Brand typography (p.6) — Playfair Display for headlines and large stats,
// Lato for body. Custom fonts don't synthesize weights/italics in RN, so
// every emphasis level needs its own face.
export const fonts = {
  display: "PlayfairDisplay_700Bold",
  displayMedium: "PlayfairDisplay_600SemiBold",
  displayItalic: "PlayfairDisplay_600SemiBold_Italic",
  sans: "Lato_400Regular",
  sansItalic: "Lato_400Regular_Italic",
  sansBold: "Lato_700Bold",
} as const;

export const cardRadius = 16;

// 4px spacing scale. Snap paddings / margins / gaps to these so the whole app
// shares one rhythm instead of ~25 near-duplicate magic numbers.
export const space = {
  0: 0,
  1: 4,
  2: 8,
  3: 12,
  4: 16,
  5: 20,
  6: 24,
  8: 32,
  10: 40,
  12: 48,
} as const;

// Corner radii. `card` is already 16; `pill` for fully-rounded chips/buttons.
export const radius = {
  chip: 10,
  card: cardRadius,
  pill: 999,
  hairline: 1,
} as const;

// The single, brand-correct elevation: a tight navy-tinted lift. Reuse this
// instead of inventing new shadow treatments so the UI stays flat and upmarket.
export const shadowSoft = Platform.select({
  web: { boxShadow: "0 2px 8px rgba(12, 46, 78, 0.05)" },
  default: {
    shadowColor: "#0C2E4E",
    shadowOpacity: 0.05,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 2 },
    elevation: 2,
  },
});

export const card = {
  backgroundColor: colors.surfaceCard,
  borderRadius: cardRadius,
  // A tight, subtle shadow + faint border. Keep it small and low-offset so it
  // reads as a clean lift on iOS rather than a muddy navy band under the card.
  borderWidth: 1,
  borderColor: "rgba(23,61,103,0.05)",
  ...shadowSoft,
} as const;

export const sectionHeader = {
  fontSize: 11,
  fontFamily: fonts.sansBold,
  textTransform: "uppercase",
  letterSpacing: 0.6,
  color: colors.inkTertiary,
} as const;

// Type scale — Playfair Display for display/title/heading, Lato for body/caption.
// Collapses the app's ~24 ad-hoc font sizes into one ladder; model big stats on
// `display` (Playfair Medium + tabular figures, per brand).
export const text = {
  display: {
    fontFamily: fonts.displayMedium,
    fontSize: 48,
    color: colors.inkPrimary,
    fontVariant: ["tabular-nums"],
  },
  title: { fontFamily: fonts.displayMedium, fontSize: 28, color: colors.inkPrimary },
  heading: { fontFamily: fonts.displayMedium, fontSize: 20, color: colors.inkPrimary },
  sectionLabel: sectionHeader,
  body: { fontFamily: fonts.sans, fontSize: 15, color: colors.inkPrimary },
  bodySm: { fontFamily: fonts.sans, fontSize: 13, color: colors.inkSecondary },
  caption: { fontFamily: fonts.sans, fontSize: 12, color: colors.inkTertiary },
} satisfies Record<string, TextStyle>;

// "$2,746,000" — negatives render as "-$310,000"
export function usd(n: number): string {
  const s = Math.abs(Math.round(n)).toLocaleString("en-US");
  return (n < 0 ? "-$" : "$") + s;
}

// "2026-06-08T19:14:00Z" → "Jun 8"
export function shortDate(iso: string): string {
  const d = new Date(iso.includes("T") ? iso : iso + "T00:00:00Z");
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// "2026-04" → "Apr"
export function monthName(month: string): string {
  const m = parseInt(month.slice(-2), 10);
  return m >= 1 && m <= 12 ? MONTHS[m - 1] : month.slice(-2);
}

// "2025-11" → "Nov 2025"
export function monthLabel(month: string): string {
  const [y] = month.split("-");
  return `${monthName(month)} ${y}`;
}
