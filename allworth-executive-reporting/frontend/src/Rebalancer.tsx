import { useEffect, useMemo, useState } from 'react';
import {
  Alert, AppBar, Box, Button, Card, CardContent, Chip, CircularProgress,
  Container, Divider, FormControlLabel, MenuItem, Stack, Switch, Table,
  TableBody, TableCell, TableHead, TableRow, TextField, Toolbar, Typography,
} from '@mui/material';
import SideNav from './components/SideNav';
import './Avantos.css';

const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';
const DEMO_CATALOG: ModelCatalog = {
  model_names: ['Allworth Balanced', 'Allworth Growth', 'Allworth Income'],
  allocations_by_model: {
    'Allworth Balanced': ['60 / 40', '55 / 45'],
    'Allworth Growth': ['80 / 20', '70 / 30'],
    'Allworth Income': ['40 / 60', '30 / 70'],
  },
};

type Account = {
  account_number: string; upload_account_id: string;
  current_strategy: string | null; total_account_value: number | null;
  cash_reserve: number | null; custodian: string | null;
  is_taxable: boolean | null; below_minimum: boolean;
};

type ModelCatalog = {
  model_names: string[];
  allocations_by_model: Record<string, string[]>;
};

type OptimizeResults = {
  optimized_portfolio: Record<string, unknown>[];
  max_tax_bill: number; total_tax: number;
  realized_gains_short: number; realized_gains_long: number;
  total_realized_gains: number; tracking_error: number;
  adjusted_allocation: Record<string, unknown>[];
  constraint_type: string;
};

const money = (value: unknown, compact = false) => new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD', maximumFractionDigits: 0,
  notation: compact ? 'compact' : 'standard',
}).format(Number(value || 0));

const num = (value: unknown, digits = 2) =>
  Number(value || 0).toLocaleString('en-US', { maximumFractionDigits: digits });

function Tile({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return <Card className="av-tile"><CardContent>
    <Typography className="av-tile__label">{label}</Typography>
    <Typography className="av-tile__value" color={tone}>{value}</Typography>
  </CardContent></Card>;
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { headers: { 'Content-Type': 'application/json' } });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error((body as { error?: string }).error || `${response.status} ${response.statusText}`);
  return body as T;
}

export default function Rebalancer() {
  const [catalog, setCatalog] = useState<ModelCatalog | null>(null);
  const [accountNumber, setAccountNumber] = useState('');
  const [account, setAccount] = useState<Account | null>(null);
  const [resolving, setResolving] = useState(false);

  const [model, setModel] = useState('');
  const [allocation, setAllocation] = useState('');
  const [stRate, setStRate] = useState('37');
  const [ltRate, setLtRate] = useState('20');
  const [taxBudget, setTaxBudget] = useState('');
  const [washSale, setWashSale] = useState(true);

  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<OptimizeResults | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (DEMO_MODE) {
      setCatalog(DEMO_CATALOG);
      return;
    }
    getJson<ModelCatalog>('/api/rebalancer/models')
      .then(setCatalog)
      .catch(e => setError(e instanceof Error ? e.message : 'Unable to load models'));
  }, []);

  const allocations = useMemo(
    () => (model && catalog ? catalog.allocations_by_model[model] || [] : []),
    [catalog, model],
  );

  const resolveAccount = async () => {
    setError(''); setAccount(null); setResults(null); setResolving(true);
    try {
      if (DEMO_MODE) {
        setAccount({ account_number: accountNumber.trim(), upload_account_id: `demo-${accountNumber.trim()}`, current_strategy: 'Legacy Moderate', total_account_value: 2_840_000, cash_reserve: 85_000, custodian: 'Fidelity', is_taxable: true, below_minimum: false });
        return;
      }
      const resolved = await getJson<Account>(`/api/rebalancer/account/${encodeURIComponent(accountNumber.trim())}`);
      setAccount(resolved);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Account lookup failed');
    } finally {
      setResolving(false);
    }
  };

  const run = async () => {
    if (!account || !model || !allocation) return;
    setError(''); setResults(null); setRunning(true);
    try {
      if (DEMO_MODE) {
        setResults({
          optimized_portfolio: [
            { Symbol: 'VTI', 'Shares Sold': 0, 'Shares Bought': 420, 'Optimized Quantity': 1840, 'Final Market Value': 488000 },
            { Symbol: 'VXUS', 'Shares Sold': 0, 'Shares Bought': 760, 'Optimized Quantity': 1960, 'Final Market Value': 132000 },
            { Symbol: 'BND', 'Shares Sold': 380, 'Shares Bought': 0, 'Optimized Quantity': 2120, 'Final Market Value': 154000 },
            { Symbol: 'AAPL', 'Shares Sold': 510, 'Shares Bought': 0, 'Optimized Quantity': 910, 'Final Market Value': 202000 },
          ],
          max_tax_bill: Number(taxBudget || 45000), total_tax: 31740,
          realized_gains_short: 28400, realized_gains_long: 106200,
          total_realized_gains: 134600, tracking_error: 0.0184,
          adjusted_allocation: [], constraint_type: taxBudget ? 'tax_budget' : 'tracking_error',
        });
        return;
      }
      const response = await fetch('/api/rebalancer/optimize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          upload_account_id: account.upload_account_id,
          model,
          allocation,
          short_term_tax_rate: Number(stRate) / 100,
          long_term_tax_rate: Number(ltRate) / 100,
          tax_budget: taxBudget.trim() ? Number(taxBudget) : undefined,
          enable_wash_sale: washSale,
        }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.error || `${response.status} ${response.statusText}`);
      setResults(body.results as OptimizeResults);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Optimization failed');
    } finally {
      setRunning(false);
    }
  };

  const trades = useMemo(() => {
    if (!results) return [];
    return results.optimized_portfolio
      .map(row => ({
        symbol: String(row['Symbol'] ?? ''),
        sold: Number(row['Shares Sold'] ?? 0),
        bought: Number(row['Shares Bought'] ?? 0),
        finalQty: Number(row['Optimized Quantity'] ?? 0),
        finalValue: Number(row['Final Market Value'] ?? 0),
      }))
      .filter(row => row.sold > 1e-6 || row.bought > 1e-6)
      .sort((a, b) => (b.sold + b.bought) - (a.sold + a.bought));
  }, [results]);

  return <div className="has-sidenav">
    <SideNav />
    <Box className="av-shell">
      <AppBar position="static" elevation={0} className="av-header"><Toolbar>
        <Box sx={{ flex: 1 }}>
          <Typography component="h1" className="av-brand">Mock Rebalancer</Typography>
          <Typography className="av-product">
            Tax-transition what-if — proposed trades only, nothing is submitted
          </Typography>
        </Box>
        <Chip label="Mock only — no trades submitted" className="av-status-chip" size="small" />
      </Toolbar></AppBar>

      <Container maxWidth="lg" sx={{ py: 3 }}>
        {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError('')}>{error}</Alert>}

        <Card sx={{ mb: 3 }}><CardContent>
          <Typography variant="subtitle1" sx={{ mb: 2, fontWeight: 600 }}>1 — Account</Typography>
          <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }}>
            <TextField label="Account number" size="small" value={accountNumber}
              onChange={e => setAccountNumber(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && resolveAccount()} />
            <Button variant="contained" onClick={resolveAccount}
              disabled={resolving || !accountNumber.trim()}>
              {resolving ? <CircularProgress size={20} /> : 'Look up'}
            </Button>
            {account && <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
              <Chip size="small" label={`Value ${money(account.total_account_value)}`} />
              <Chip size="small" label={`Strategy: ${account.current_strategy || '—'}`} />
              <Chip size="small" label={account.custodian || 'Unknown custodian'} />
              <Chip size="small" color={account.is_taxable ? 'default' : 'warning'}
                label={account.is_taxable === false ? 'Non-taxable' : 'Taxable'} />
              {account.below_minimum &&
                <Chip size="small" color="error" label="Below $2,000 minimum" />}
            </Stack>}
          </Stack>
        </CardContent></Card>

        <Card sx={{ mb: 3 }}><CardContent>
          <Typography variant="subtitle1" sx={{ mb: 2, fontWeight: 600 }}>2 — Target &amp; constraints</Typography>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ alignItems: 'center' }}>
            <TextField select label="Target model" size="small" sx={{ minWidth: 260 }}
              value={model} onChange={e => { setModel(e.target.value); setAllocation(''); }}>
              {(catalog?.model_names || []).map(name => <MenuItem key={name} value={name}>{name}</MenuItem>)}
            </TextField>
            <TextField select label="Allocation" size="small" sx={{ minWidth: 130 }}
              value={allocation} onChange={e => setAllocation(e.target.value)} disabled={!model}>
              {allocations.map(a => <MenuItem key={a} value={a}>{a}</MenuItem>)}
            </TextField>
            <TextField label="Short-term rate %" size="small" sx={{ width: 140 }}
              value={stRate} onChange={e => setStRate(e.target.value)} />
            <TextField label="Long-term rate %" size="small" sx={{ width: 140 }}
              value={ltRate} onChange={e => setLtRate(e.target.value)} />
            <TextField label="Tax budget $ (optional)" size="small" sx={{ width: 180 }}
              value={taxBudget} onChange={e => setTaxBudget(e.target.value)} />
            <FormControlLabel control={
              <Switch checked={washSale} onChange={e => setWashSale(e.target.checked)} />
            } label="Wash-sale rules" />
            <Button variant="contained" color="primary" onClick={run}
              disabled={running || !account || !model || !allocation || account.below_minimum}>
              {running ? <CircularProgress size={20} /> : 'Run mock rebalance'}
            </Button>
          </Stack>
        </CardContent></Card>

        {running && <Alert severity="info" sx={{ mb: 2 }}>
          Solving — lot-level convex optimization can take up to a minute for large accounts…
        </Alert>}

        {results && <>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 3 }}>
            <Tile label="Estimated tax" value={money(results.total_tax)}
              tone={results.total_tax > 0 ? 'warning.main' : 'success.main'} />
            <Tile label="Realized gains (ST)" value={money(results.realized_gains_short)} />
            <Tile label="Realized gains (LT)" value={money(results.realized_gains_long)} />
            <Tile label="Total realized" value={money(results.total_realized_gains)} />
            <Tile label="Tracking error" value={`${num(results.tracking_error * 100, 2)}%`} />
          </Stack>

          <Card><CardContent>
            <Stack direction="row" spacing={1} sx={{ mb: 1, alignItems: 'center' }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>Proposed trades</Typography>
              <Chip size="small" label={`${trades.length} lots traded`} />
              <Box sx={{ flex: 1 }} />
              <Chip size="small" color="warning" variant="outlined" label="Not submitted" />
            </Stack>
            <Divider sx={{ mb: 1 }} />
            {trades.length === 0
              ? <Typography variant="body2" sx={{ opacity: 0.7 }}>No trades required — portfolio already within constraints.</Typography>
              : <Table size="small">
                  <TableHead><TableRow>
                    <TableCell>Symbol</TableCell>
                    <TableCell align="right">Shares sold</TableCell>
                    <TableCell align="right">Shares bought</TableCell>
                    <TableCell align="right">Final quantity</TableCell>
                    <TableCell align="right">Final value</TableCell>
                  </TableRow></TableHead>
                  <TableBody>
                    {trades.map((row, index) => <TableRow key={`${row.symbol}-${index}`}>
                      <TableCell>{row.symbol}</TableCell>
                      <TableCell align="right">{row.sold > 1e-6 ? num(row.sold) : '—'}</TableCell>
                      <TableCell align="right">{row.bought > 1e-6 ? num(row.bought) : '—'}</TableCell>
                      <TableCell align="right">{num(row.finalQty)}</TableCell>
                      <TableCell align="right">{money(row.finalValue)}</TableCell>
                    </TableRow>)}
                  </TableBody>
                </Table>}
          </CardContent></Card>
        </>}
      </Container>
    </Box>
  </div>;
}
