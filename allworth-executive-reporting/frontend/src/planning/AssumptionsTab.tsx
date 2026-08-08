import { useCallback, useEffect, useState } from 'react';
import {
  Alert, Box, Card, CardContent, Chip, CircularProgress, Table, TableBody,
  TableCell, TableHead, TableRow, Typography,
} from '@mui/material';
import { planningApi, type CapitalMarketAssumptions } from '../services/planningApi';
import { pct } from './shared';

const CORRELATION_LABEL: Record<string, string> = {
  same_equity: 'Equity vs equity',
  same_bond: 'Bond vs bond',
  same_other: 'Within other buckets',
  cross_bucket: 'Across buckets',
  equity_bond: 'Equity vs bond',
};

export default function AssumptionsTab({ onError }: { onError: (message: string) => void }) {
  const [cma, setCma] = useState<CapitalMarketAssumptions | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try { setCma(await planningApi.capitalMarketAssumptions()); }
    catch (e) { onError(e instanceof Error ? e.message : 'Unable to load assumptions'); }
    finally { setLoading(false); }
  }, [onError]);

  useEffect(() => { void load(); }, [load]);

  if (loading) return <Box className="plan-loading"><CircularProgress /></Box>;
  if (!cma) return <Box className="plan-panel"><Alert severity="info">Capital-market assumptions unavailable.</Alert></Box>;

  const classes = Object.entries(cma.asset_classes).sort(([a], [b]) => a.localeCompare(b));

  return <Box className="plan-panel">
    <Card><CardContent>
      <Typography variant="h6">Capital-market assumptions</Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        {cma.version} · as of {cma.as_of} · {cma.source}
      </Typography>
      {cma.warnings.map(warning => <Alert key={warning} severity="warning" sx={{ mb: 2 }}>{warning}</Alert>)}
      <Table size="small">
        <TableHead><TableRow>
          <TableCell>Asset class</TableCell><TableCell>Bucket</TableCell>
          <TableCell align="right">Expected return</TableCell><TableCell align="right">Volatility</TableCell>
          <TableCell>Sources</TableCell>
        </TableRow></TableHead>
        <TableBody>{classes.map(([name, row]) =>
          <TableRow key={name}>
            <TableCell>{name}</TableCell>
            <TableCell><Chip size="small" label={row.bucket.replaceAll('_', ' ')} /></TableCell>
            <TableCell align="right">{pct(row.expected_return, 1)}</TableCell>
            <TableCell align="right">{pct(row.std_dev, 1)}</TableCell>
            <TableCell><Typography variant="caption">{row.expected_return_source} · {row.volatility_source}</Typography></TableCell>
          </TableRow>)}</TableBody>
      </Table>
    </CardContent></Card>
    <Card sx={{ mt: 2.5 }}><CardContent>
      <Typography variant="h6">Correlation policy</Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>Pairwise correlations used to build the Monte Carlo covariance matrix.</Typography>
      <Table size="small" sx={{ maxWidth: 480 }}>
        <TableBody>{Object.entries(cma.correlations).map(([key, value]) =>
          <TableRow key={key}>
            <TableCell>{CORRELATION_LABEL[key] || key.replaceAll('_', ' ')}</TableCell>
            <TableCell align="right">{Number(value).toFixed(2)}</TableCell>
          </TableRow>)}</TableBody>
      </Table>
    </CardContent></Card>
  </Box>;
}
