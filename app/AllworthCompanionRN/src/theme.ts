// Brand — verified 2026-06-09 from allworth-financial-logo-color.svg
export const colors = {
  allworthNavy: "#173D67",
  allworthAccent: "#3E71B7",

  surfacePrimary: "#FAFAF8",
  surfaceCard: "#FFFFFF",

  inkPrimary: "#0B1220",
  inkSecondary: "rgba(11,18,32,0.60)",
  inkTertiary: "rgba(11,18,32,0.38)",
  hairline: "rgba(11,18,32,0.08)",
  inkFaint: "rgba(11,18,32,0.05)",

  // Semantic only — money movement, never decorative
  gainGreen: "#00C805",
  lossRed: "#CF3A4A",
  attention: "#C77B17",
};

// Brand typography — Lato (body) + Playfair Display (display), per allworthfinancial.com
export const fonts = {
  display: "PlayfairDisplay_700Bold",
  displayMedium: "PlayfairDisplay_600SemiBold",
  sans: "Lato_400Regular",
  sansBold: "Lato_700Bold",
} as const;

export const cardRadius = 16;

export const card = {
  backgroundColor: colors.surfaceCard,
  borderRadius: cardRadius,
  shadowColor: "#000",
  shadowOpacity: 0.05,
  shadowRadius: 12,
  shadowOffset: { width: 0, height: 4 },
  elevation: 2,
} as const;

export const sectionHeader = {
  fontSize: 11,
  fontWeight: "600",
  textTransform: "uppercase",
  letterSpacing: 0.6,
  color: colors.inkTertiary,
} as const;

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
