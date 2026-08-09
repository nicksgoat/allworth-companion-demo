import { lazy, Suspense, useState } from 'react';
import { Tab, Tabs, Alert, Box, LinearProgress } from '@mui/material';
import { ThemeProvider } from '@mui/material/styles';
import AuthControl from './components/AuthControl';
import { TabPanel } from './components/TabPanel';
import ShareTool from './components/ShareTool';
import { ToolPage, ToolPanel } from './components/ToolPage';
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
      <ToolPage
        eyebrow="Portfolio tools"
        title="Bond Analyzer"
        description="Build fixed-income ladders, inspect account exposure, and produce client-ready analysis."
        width="full"
        actions={
          <>
          <ShareTool toolId="bond_analyzer" toolName="Bond Analyzer" />
          <AuthControl />
          </>
        }
      >
        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        <ToolPanel flush>
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
        </ToolPanel>
      </ToolPage>
    </ThemeProvider>
  );
}
