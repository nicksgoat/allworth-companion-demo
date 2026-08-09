import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert, Box, Button, Card, CardContent, CircularProgress, FormControl, InputLabel,
  MenuItem, Select, Stack, Table, TableBody, TableCell, TableHead, TableRow, TextField, Typography,
} from '@mui/material';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, XAxis, YAxis } from 'recharts';
import { ChartContainer, ChartLegend, ChartTooltip } from '../components/ui/chart';
import { planningApi, type LifecyclePlan } from '../services/planningApi';
import { Kpi, chartColors, money, pct } from './shared';

const SENSITIVITY_PARAMS = [
  { value: 'retirement_age', label: 'Retirement age' },
  { value: 'risk_tolerance', label: 'Risk tolerance' },
  { value: 'nondiscretionary_consumption', label: 'Essential spending' },
  { value: 'annuitize_fraction', label: 'Annuitized fraction' },
  { value: 'longevity_adjustment', label: 'Longevity adjustment' },
];

export default function LifecycleTab({ scenario, onError }: { scenario: string; onError: (message: string) => void }) {
  const [plan, setPlan] = useState<LifecyclePlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [param, setParam] = useState('retirement_age');
  const [valuesText, setValuesText] = useState('62, 65, 68');
  const [sensitivity, setSensitivity] = useState<Array<{ value: number | string; result: LifecyclePlan }>>([]);
  const [sensitivityRunning, setSensitivityRunning] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { setPlan(await planningApi.lifecyclePlan(scenario)); }
    catch (e) { onError(e instanceof Error ? e.message : 'Lifecycle plan failed'); }
    finally { setLoading(false); }
  }, [scenario, onError]);

  useEffect(() => { setPlan(null); setSensitivity([]); void load(); }, [load]);

  async function runSensitivity() {
    const values = valuesText.split(',').map(x => x.trim()).filter(Boolean)
      .map(x => (Number.isNaN(Number(x)) ? x : Number(x)));
    if (!values.length) return;
    setSensitivityRunning(true);
    try { setSensitivity((await planningApi.lifecycleSensitivity(scenario, param, values)).results); }
    catch (e) { onError(e instanceof Error ? e.message : 'Sensitivity run failed'); }
    finally { setSensitivityRunning(false); }
  }

  const glide = useMemo(() => (plan?.glide_path || []).map(row => ({
    age: row.age,
    'Domestic stock': row.domestic_stock * 100,
    'Global stock': row.global_stock * 100,
    'Bonds & cash': row.bonds_cash * 100,
  })), [plan]);

  const consumption = useMemo(() => (plan?.consumption_path || []).map(row => ({
    age: row.age,
    Essential: row.nondiscretionary,
    Discretionary: row.discretionary,
    'Annuity floor': row.annuity_floor,
  })), [plan]);

  if (loading && !plan) return <Box className="plan-loading"><CircularProgress /></Box>;
  if (!plan) return <Box className="plan-panel"><Alert severity="info">Lifecycle plan unavailable for this scenario.</Alert></Box>;

  const sheet = plan.economic_balance_sheet;
  return <Box className="plan-panel">
    <Box className="plan-metrics">
      <Kpi label="Financial wealth" value={money(sheet.financial_wealth, true)} />
      <Kpi label="Human capital" value={money(sheet.human_capital, true)} />
      <Kpi label="Lifetime liabilities" value={money(sheet.liabilities, true)} />
      <Kpi label="Economic net worth" value={money(sheet.economic_net_worth, true)} tone={sheet.economic_net_worth >= 0 ? 'gain' : 'loss'} />
      <Kpi label={`Bequest (${plan.bequest.type})`} value={money(plan.bequest.amount, true)} />
    </Box>
    {plan.warnings.map(warning => <Alert key={warning} severity="info" sx={{ mb: 2 }}>{warning}</Alert>)}
    <Card><CardContent>
      <Typography variant="h6">Recommended glide path</Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>Equity allocation declines as human capital converts to financial wealth (Idzorek–Kaplan lifecycle model).</Typography>
      <ChartContainer width="100%" height={320}>
        <AreaChart data={glide} stackOffset="expand">
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="age" /><YAxis tickFormatter={v => pct(v)} />
          <ChartTooltip formatter={(value: unknown) => `${Number(value).toFixed(1)}%`} /><ChartLegend />
          <Area dataKey="Domestic stock" stackId="1" stroke={chartColors.nightBlue} fill={chartColors.nightBlue} />
          <Area dataKey="Global stock" stackId="1" stroke={chartColors.sky} fill={chartColors.sky} />
          <Area dataKey="Bonds & cash" stackId="1" stroke={chartColors.gold} fill={chartColors.gold} />
        </AreaChart>
      </ChartContainer>
    </CardContent></Card>
    <Card sx={{ mt: 2.5 }}><CardContent>
      <Typography variant="h6">Sustainable consumption path</Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>Essential spending, discretionary consumption, and the annuitized floor by age.</Typography>
      <ChartContainer width="100%" height={300}>
        <BarChart data={consumption}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="age" /><YAxis tickFormatter={v => money(v, true)} />
          <ChartTooltip formatter={v => money(v)} /><ChartLegend />
          <Bar dataKey="Essential" stackId="c" fill={chartColors.nightBlue} />
          <Bar dataKey="Discretionary" stackId="c" fill={chartColors.evergreen} />
          <Bar dataKey="Annuity floor" stackId="c" fill={chartColors.gold} />
        </BarChart>
      </ChartContainer>
    </CardContent></Card>
    <Card sx={{ mt: 2.5 }}><CardContent>
      <Typography variant="h6">Sensitivity analysis</Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>Re-run the lifecycle model across a range of one input.</Typography>
      <Stack direction="row" sx={{ gap: 2, alignItems: 'center', flexWrap: 'wrap', mb: 2 }}>
        <FormControl size="small" sx={{ minWidth: 220 }}>
          <InputLabel>Parameter</InputLabel>
          <Select value={param} label="Parameter" onChange={e => setParam(e.target.value)}>
            {SENSITIVITY_PARAMS.map(item => <MenuItem key={item.value} value={item.value}>{item.label}</MenuItem>)}
          </Select>
        </FormControl>
        <TextField size="small" label="Values (comma-separated, max 8)" value={valuesText} onChange={e => setValuesText(e.target.value)} sx={{ minWidth: 260 }} />
        <Button variant="contained" onClick={runSensitivity} disabled={sensitivityRunning}>{sensitivityRunning ? 'Running…' : 'Run sensitivity'}</Button>
      </Stack>
      {sensitivity.length > 0 && <Table size="small">
        <TableHead><TableRow>
          <TableCell>{SENSITIVITY_PARAMS.find(x => x.value === param)?.label || param}</TableCell>
          <TableCell align="right">Economic net worth</TableCell>
          <TableCell align="right">Bequest</TableCell>
          <TableCell align="right">First-year consumption</TableCell>
          <TableCell align="right">Starting equity</TableCell>
        </TableRow></TableHead>
        <TableBody>{sensitivity.map(row =>
          <TableRow key={String(row.value)}>
            <TableCell>{String(row.value)}</TableCell>
            <TableCell align="right">{money(row.result.economic_balance_sheet.economic_net_worth)}</TableCell>
            <TableCell align="right">{money(row.result.bequest.amount)}</TableCell>
            <TableCell align="right">{money(row.result.consumption_path[0]?.total_consumption)}</TableCell>
            <TableCell align="right">{pct(row.result.glide_path[0]?.constrained_equity, 1)}</TableCell>
          </TableRow>)}</TableBody>
      </Table>}
    </CardContent></Card>
  </Box>;
}
