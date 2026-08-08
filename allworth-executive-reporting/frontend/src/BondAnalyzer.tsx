import { lazy, Suspense, useState } from 'react';
import { Container, Tab, Tabs, Alert, Box, LinearProgress } from '@mui/material';
import { ThemeProvider } from '@mui/material/styles';
import AuthControl from './components/AuthControl';
import { TabPanel } from './components/TabPanel';
import SideNav from './components/SideNav';
import ShareTool from './components/ShareTool';
import { colors, muiTheme } from './theme';
import './BondAnalyzer.css';

const AccountAnalyzer = lazy(() => import('./components/AccountAnalyzer'));
const BondLadderWorkspace = lazy(() => import('./components/BondLadderWorkspace'));
const SamplePortfolio = lazy(() => import('./components/SamplePortfolio'));

export default function BondAnalyzer() {
  const [tab, setTab] = useState(0);
  const [error, setError] = useState<string | null>(null);

  return (
    <ThemeProvider theme={muiTheme}>
    <div className="has-sidenav">
    <SideNav />
    <Box sx={{ minHeight: '100vh', backgroundColor: colors.surfacePrimary }}>
      {/* ── Allworth hero header ─────────────────────────────────────────── */}
      <div className="aw-hero">
        <div className="aw-hero__topline">
          <ShareTool toolId="bond_analyzer" toolName="Bond Analyzer" />
          <AuthControl />
        </div>
        <div>
          <p className="aw-hero__eyebrow">Allworth Financial</p>
          <h1 className="aw-hero__title">Bond Analyzer</h1>
          <p className="aw-hero__subtitle">Fixed-income portfolio analysis and reporting</p>
        </div>
      </div>

      {/* ── Main content ─────────────────────────────────────────────────── */}
      <Container maxWidth="xl" sx={{ py: 3, px: { xs: 1, sm: 2, md: 3 } }}>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        <Box
          sx={{
            backgroundColor: colors.surfaceCard,
            borderRadius: 4,
            border: '1px solid rgba(23,61,103,0.05)',
            boxShadow: '0 2px 8px rgba(12,46,78,0.05)',
            overflow: 'hidden',
          }}
        >
          <Tabs
            value={tab}
            onChange={(_, v) => setTab(v)}
            sx={{
              borderBottom: `1px solid ${colors.hairline}`,
              px: 2,
              backgroundColor: colors.surfaceCard,
            }}
          >
            <Tab label="Bond Ladder" id="ba-0" aria-controls="ba-panel-0" />
            <Tab label="Account Lookup" id="ba-1" aria-controls="ba-panel-1" />
            <Tab label="Sample Portfolio" id="ba-2" aria-controls="ba-panel-2" />
          </Tabs>

          <Box sx={{ p: 3 }}>
            <Suspense fallback={<LinearProgress sx={{ my: 4 }} />}>
              <TabPanel value={tab} index={0} idPrefix="ba">
                <BondLadderWorkspace />
              </TabPanel>

              <TabPanel value={tab} index={1} idPrefix="ba">
                <AccountAnalyzer />
              </TabPanel>

              <TabPanel value={tab} index={2} idPrefix="ba">
                <SamplePortfolio />
              </TabPanel>
            </Suspense>
          </Box>
        </Box>
      </Container>
    </Box>
    </div>
    </ThemeProvider>
  );
}
