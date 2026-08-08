import { lazy, Suspense, useState } from 'react';
import { Box, LinearProgress, Tab, Tabs } from '@mui/material';
import { colors } from '../theme';

const BondLadderView = lazy(() => import('./BondLadderView'));
const CalledBondsView = lazy(() => import('./CalledBondsView'));

export default function BondLadderWorkspace() {
  const [page, setPage] = useState(0);

  return (
    <Box>
      <Tabs
        value={page}
        onChange={(_, value) => setPage(value)}
        aria-label="Bond ladder pages"
        sx={{
          px: 1,
          minHeight: 40,
          borderBottom: `1px solid ${colors.hairline}`,
          '& .MuiTab-root': { minHeight: 40, py: 0.75 },
        }}
      >
        <Tab label="Current Holdings" />
        <Tab label="Recently Called" />
      </Tabs>
      <Suspense fallback={<LinearProgress sx={{ my: 3 }} />}>
        {page === 0 ? <BondLadderView /> : <CalledBondsView />}
      </Suspense>
    </Box>
  );
}
