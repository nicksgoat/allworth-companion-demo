/**
 * Allworth Financial brand tokens — mirrored from the mobile app's theme.ts.
 * Source of truth: ALW001_01_Brand_Dashboard_DEC2024.pdf (brand deck)
 */
import { createTheme } from '@mui/material/styles';

// ─── Color Palette ─────────────────────────────────────────────────────────────

export const colors = {
  // Primary palette (brand deck p.7)
  allworthNavy: '#173D67',    // Indigo Blue / PMS 295C — wordmark
  allworthAccent: '#3E71B7',  // Cerulean Blue / PMS 2144C — Iris symbol

  // Neutrals — backgrounds, text boxes, table fields
  surfacePrimary: '#F3F4F4',  // Feather Gray — page background
  surfaceCard: '#FFFFFF',
  beige: '#EBE9DD',
  linen: '#F3F2E5',
  ice: '#EDF2F7',

  // Monotone — copy and stats
  inkPrimary: '#000000',
  inkSecondary: '#595959',    // Dark Gray
  inkTertiary: '#828282',     // Medium Gray
  hairline: '#E6E6E6',        // Pale Gray — dividers
  inkFaint: '#E6E6E6',        // Pale Gray — chip fills, tracks, skeletons

  // Semantic money movement — mapped onto secondary palette
  gain: '#436434',            // Evergreen
  loss: '#D26D37',            // Pumpkin
  attention: '#D26D37',

  // Chart palette — infographics only (brand deck p.7)
  chartNightBlue: '#0C2E4E',
  chartSky: '#289FDA',
  chartEvergreen: '#436434',
  chartGold: '#A99C6C',
  chartPumpkin: '#D26D37',
  chartLightGray: '#BEBEBE',
};

// Ordered chart palette — use in sequence for multi-series charts
export const chartPalette = [
  colors.chartNightBlue,
  colors.chartSky,
  colors.chartGold,
  colors.chartEvergreen,
  colors.chartPumpkin,
  colors.chartLightGray,
];

// ─── Card Surface ───────────────────────────────────────────────────────────────

export const cardStyle = {
  backgroundColor: colors.surfaceCard,
  borderRadius: 16,
  border: '1px solid rgba(23,61,103,0.05)',
  boxShadow: '0 2px 8px rgba(12, 46, 78, 0.05)',
};

// ─── Section Header ─────────────────────────────────────────────────────────────
// Lato Bold, 11px, uppercase, letter-spacing 0.6 — mirrors mobile sectionHeader

export const sectionHeaderStyle = {
  fontSize: 11,
  fontFamily: "'Lato', sans-serif",
  fontWeight: 700,
  textTransform: 'uppercase' as const,
  letterSpacing: 0.6,
  color: colors.inkTertiary,
};

// ─── Hero Gradient ──────────────────────────────────────────────────────────────
// Night Blue → Indigo gradient with a soft cerulean radial glow (brand hero)

export const heroGradient =
  'linear-gradient(160deg, #0C2E4E 0%, #173D67 100%)';

// ─── MUI Theme ──────────────────────────────────────────────────────────────────

export const muiTheme = createTheme({
  palette: {
    primary:    { main: colors.allworthNavy, contrastText: '#ffffff' },
    secondary:  { main: colors.allworthAccent },
    background: { default: colors.surfacePrimary, paper: colors.surfaceCard },
    text: {
      primary:   colors.inkPrimary,
      secondary: colors.inkSecondary,
    },
    success: { main: colors.gain },
    warning: { main: colors.loss },
    error:   { main: colors.loss },
    divider: colors.hairline,
  },

  typography: {
    fontFamily: "'Lato', sans-serif",
    // Display / stat headings → Playfair Display
    h1: { fontFamily: "'Playfair Display', serif", fontWeight: 600 },
    h2: { fontFamily: "'Playfair Display', serif", fontWeight: 600 },
    h3: { fontFamily: "'Playfair Display', serif", fontWeight: 600 },
    h4: { fontFamily: "'Playfair Display', serif", fontWeight: 600 },
    h5: { fontFamily: "'Playfair Display', serif", fontWeight: 600 },
    // Sub-headings stay Lato Bold
    h6:       { fontFamily: "'Lato', sans-serif", fontWeight: 700 },
    subtitle1: { fontFamily: "'Lato', sans-serif" },
    subtitle2: { fontFamily: "'Lato', sans-serif", fontWeight: 700 },
    body1:     { fontFamily: "'Lato', sans-serif" },
    body2:     { fontFamily: "'Lato', sans-serif" },
    button:    { fontFamily: "'Lato', sans-serif", fontWeight: 700, textTransform: 'none' },
    caption:   { fontFamily: "'Lato', sans-serif", color: colors.inkTertiary },
    overline:  { fontFamily: "'Lato', sans-serif", fontWeight: 700, letterSpacing: 0.6 },
  },

  shape: { borderRadius: 16 },

  components: {
    MuiCard: {
      styleOverrides: {
        root: { ...cardStyle },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: { ...cardStyle },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: { borderRadius: 8, textTransform: 'none', fontWeight: 700 },
        contained: {
          backgroundColor: colors.allworthNavy,
          '&:hover': { backgroundColor: colors.chartNightBlue },
        },
        outlined: {
          borderColor: colors.allworthNavy,
          color: colors.allworthNavy,
          '&:hover': { borderColor: colors.chartNightBlue, backgroundColor: 'rgba(23,61,103,0.04)' },
        },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: {
          fontFamily: "'Lato', sans-serif",
          fontWeight: 700,
          textTransform: 'none',
          fontSize: 14,
          color: colors.inkSecondary,
          '&.Mui-selected': { color: colors.allworthNavy },
        },
      },
    },
    MuiTabs: {
      styleOverrides: {
        indicator: { backgroundColor: colors.allworthNavy },
      },
    },
    MuiTableHead: {
      styleOverrides: {
        root: {
          '& .MuiTableCell-head': {
            backgroundColor: colors.surfacePrimary,
            color: colors.inkTertiary,
            fontFamily: "'Lato', sans-serif",
            fontWeight: 700,
            fontSize: 11,
            textTransform: 'uppercase',
            letterSpacing: 0.6,
            borderBottom: `1px solid ${colors.hairline}`,
          },
        },
      },
    },
    MuiTableRow: {
      styleOverrides: {
        root: {
          '&:hover': { backgroundColor: colors.ice },
          '& .MuiTableCell-body': {
            fontFamily: "'Lato', sans-serif",
            borderBottom: `1px solid ${colors.hairline}`,
          },
        },
      },
    },
    MuiAlert: {
      styleOverrides: {
        root: { borderRadius: 12, fontFamily: "'Lato', sans-serif" },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { fontFamily: "'Lato', sans-serif", fontWeight: 700 },
      },
    },
    MuiCssBaseline: {
      styleOverrides: {
        body: {
          backgroundColor: colors.surfacePrimary,
          fontFamily: "'Lato', sans-serif",
        },
      },
    },
  },
});
