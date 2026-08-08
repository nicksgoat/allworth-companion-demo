import { useMemo, useRef, useState } from 'react';
import {
  Alert, Box, Button, Card, CardContent, Chip, FormControl, InputLabel, MenuItem,
  Select, Stack, Table, TableBody, TableCell, TableHead, TableRow, TextField, Typography,
} from '@mui/material';
import PresentToAllOutlinedIcon from '@mui/icons-material/PresentToAllOutlined';
import { Area, AreaChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { planningApi, type CompareScenario, type RothAnalysis, type Scenario, type SolveResult, type StressResult } from '../services/planningApi';
import { Kpi, chartColors, money } from './shared';

const STRESS_KINDS = [
  { kind: 'crash' as const, label: 'Market crash', hint: '-30% return in year one' },
  { kind: 'low_return' as const, label: 'Low returns', hint: '1% returns for life' },
  { kind: 'inflation' as const, label: 'High inflation', hint: '+2% inflation for life' },
  { kind: 'longevity' as const, label: 'Longevity', hint: 'Plan to age 105' },
];

const COMPARE_COLORS = [chartColors.nightBlue, chartColors.pumpkin, chartColors.evergreen, chartColors.gold];

interface Props {
  scenario: string;
  scenarios: Scenario[];
  householdId: string;
  chart: Array<Record<string, number | string>>;
  retirementAge: string;
  annualSpending: string;
  applying: boolean;
  onRetirementAge: (value: string) => void;
  onAnnualSpending: (value: string) => void;
  onApply: () => void;
  onError: (message: string) => void;
}

export default function DecisionTab({ scenario, scenarios, householdId, chart, retirementAge, annualSpending, applying, onRetirementAge, onAnnualSpending, onApply, onError }: Props) {
  const panelRef = useRef<HTMLDivElement>(null);
  const [stress, setStress] = useState<StressResult | null>(null);
  const [stressKind, setStressKind] = useState('');
  const [stressRunning, setStressRunning] = useState(false);
  const [solveTarget, setSolveTarget] = useState('1000000');
  const [solveResult, setSolveResult] = useState<SolveResult | null>(null);
  const [solving, setSolving] = useState(false);
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [comparison, setComparison] = useState<CompareScenario[]>([]);
  const [comparing, setComparing] = useState(false);
  const [roth, setRoth] = useState<RothAnalysis | null>(null);
  const [rothRunning, setRothRunning] = useState(false);

  async function runRoth() {
    setRothRunning(true);
    try { setRoth(await planningApi.rothConversion(scenario)); }
    catch (e) { onError(e instanceof Error ? e.message : 'Roth analysis failed'); }
    finally { setRothRunning(false); }
  }

  async function runStress(kind: 'crash' | 'low_return' | 'inflation' | 'longevity') {
    setStressRunning(true);
    setStressKind(kind);
    try { setStress(await planningApi.stress(scenario, kind)); }
    catch (e) { onError(e instanceof Error ? e.message : 'Stress test failed'); }
    finally { setStressRunning(false); }
  }

  async function runSolve() {
    setSolving(true);
    try { setSolveResult(await planningApi.solve(scenario, solveTarget)); }
    catch (e) { onError(e instanceof Error ? e.message : 'Solver failed'); }
    finally { setSolving(false); }
  }

  async function runCompare() {
    if (compareIds.length < 2) return;
    setComparing(true);
    try { setComparison((await planningApi.compare(householdId, compareIds)).scenarios); }
    catch (e) { onError(e instanceof Error ? e.message : 'Comparison failed'); }
    finally { setComparing(false); }
  }

  const compareChart = useMemo(() => {
    const byYear = new Map<number, Record<string, number>>();
    comparison.forEach(item => item.series.forEach(point => {
      const row = byYear.get(point.year) || { year: point.year };
      row[item.name] = Number(point.net_worth);
      byYear.set(point.year, row);
    }));
    return [...byYear.values()].sort((a, b) => Number(a.year) - Number(b.year));
  }, [comparison]);

  const stressChart = useMemo(() => (stress?.projection.rows || []).map(row => ({
    year: row.year, stressed: Number(row.net_worth),
  })), [stress]);

  function togglePresentation() {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void panelRef.current?.requestFullscreen();
  }

  return <Box ref={panelRef} className="plan-panel plan-present">
    <Stack direction="row" sx={{ justifyContent: 'flex-end', mb: 1 }}>
      <Button size="small" startIcon={<PresentToAllOutlinedIcon />} onClick={togglePresentation}>Present</Button>
    </Stack>
    <Box className="plan-decision">
      <Card><CardContent>
        <Typography variant="h6">Decision levers</Typography>
        <Typography color="text.secondary">Adjusting levers recomputes the complete tax-aware ledger.</Typography>
        <Stack sx={{ gap: 2, mt: 3 }}>
          <TextField label="Retirement age" type="number" value={retirementAge} onChange={e => onRetirementAge(e.target.value)} slotProps={{ htmlInput: { min: 50, max: 80 } }} />
          <TextField label="Annual living expenses" type="number" value={annualSpending} onChange={e => onAnnualSpending(e.target.value)} slotProps={{ htmlInput: { min: 0, step: 1000 } }} />
          <Button variant="contained" onClick={onApply} disabled={applying}>{applying ? 'Recomputing…' : 'Apply to working scenario'}</Button>
        </Stack>
        <Typography variant="h6" sx={{ mt: 4 }}>Savings solver</Typography>
        <Typography color="text.secondary">Monthly savings needed to reach a target ending balance.</Typography>
        <Stack sx={{ gap: 2, mt: 2 }}>
          <TextField label="Target ending assets" type="number" value={solveTarget} onChange={e => setSolveTarget(e.target.value)} slotProps={{ htmlInput: { min: 0, step: 50000 } }} />
          <Button variant="outlined" onClick={runSolve} disabled={solving}>{solving ? 'Solving…' : 'Solve monthly savings'}</Button>
          {solveResult && <Alert severity={solveResult.achieved ? 'success' : 'warning'}>
            {solveResult.achieved
              ? <>Save <strong>{money(solveResult.value)}/month</strong> to reach {money(solveResult.target)} ({solveResult.iterations} iterations).</>
              : <>Target {money(solveResult.target)} was not reachable within solver bounds (best: {money(solveResult.value)}/month).</>}
          </Alert>}
        </Stack>
      </CardContent></Card>
      <Card><CardContent>
        <Typography variant="h6">Scenario impact</Typography>
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={chart}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="age" /><YAxis tickFormatter={v => money(v, true)} />
            <Tooltip formatter={v => money(v)} />
            <Area type="monotone" dataKey="netWorth" name="Net worth" stroke={chartColors.nightBlue} fill={chartColors.nightBlue} fillOpacity={0.12} strokeWidth={3} />
          </AreaChart>
        </ResponsiveContainer>
      </CardContent></Card>
    </Box>

    <Card sx={{ mt: 2.5 }}><CardContent>
      <Typography variant="h6">Stress tests</Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>One-click adverse-condition reruns of the full projection.</Typography>
      <Stack direction="row" sx={{ gap: 1.5, flexWrap: 'wrap' }}>
        {STRESS_KINDS.map(item =>
          <Button key={item.kind} variant={stress?.kind === item.kind ? 'contained' : 'outlined'}
            onClick={() => runStress(item.kind)} disabled={stressRunning} title={item.hint}>
            {stressRunning && stressKind === item.kind ? 'Running…' : item.label}
          </Button>)}
      </Stack>
      {stress && <Box sx={{ mt: 3 }}>
        <Box className="plan-metrics" sx={{ gridTemplateColumns: 'repeat(3, minmax(0,1fr))' }}>
          <Kpi label={`${STRESS_KINDS.find(x => x.kind === stress.kind)?.label || stress.kind} — ending assets`} value={money(stress.projection.ending_net_worth)} />
          <Kpi label="Impact vs base plan" value={money(stress.delta_ending_net_worth)} tone={Number(stress.delta_ending_net_worth) < 0 ? 'loss' : 'gain'} />
          <Kpi label="First shortfall" value={stress.projection.first_shortfall_year ? String(stress.projection.first_shortfall_year) : 'None'} tone={stress.projection.first_shortfall_year ? 'loss' : 'gain'} />
        </Box>
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={stressChart}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="year" /><YAxis tickFormatter={v => money(v, true)} />
            <Tooltip formatter={v => money(v)} />
            <Line dataKey="stressed" name="Stressed net worth" stroke={chartColors.pumpkin} strokeWidth={3} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </Box>}
    </CardContent></Card>

    <Card sx={{ mt: 2.5 }}><CardContent>
      <Typography variant="h6">Roth conversion analyzer</Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        Multi-year conversion ladders evaluated through the full tax-aware ledger — bracket
        fills are probed against the engine's own tax function, so Social Security phase-in,
        RMD, and deduction interactions are captured.
      </Typography>
      <Button variant="contained" onClick={runRoth} disabled={rothRunning}>
        {rothRunning ? 'Analyzing…' : 'Analyze conversions'}
      </Button>
      {roth && <Box sx={{ mt: 2 }}>
        {roth.recommended
          ? <Alert severity="success">Recommended: <strong>{roth.recommended.label}</strong> — {money(roth.recommended.annual_conversion)}/yr
            for {roth.window_years} years improves projected after-tax wealth by {money(roth.recommended.ending_after_tax_delta)}.</Alert>
          : <Alert severity="info">{roth.warnings.join(' ') || 'No conversion ladder improves after-tax wealth under current assumptions.'}</Alert>}
        {roth.candidates.length > 0 && <Table size="small" sx={{ mt: 2 }}>
          <TableHead><TableRow>
            <TableCell>Strategy</TableCell><TableCell align="right">Annual conversion</TableCell>
            <TableCell align="right">Total converted</TableCell>
            <TableCell align="right">Lifetime tax Δ</TableCell>
            <TableCell align="right">After-tax wealth Δ</TableCell>
            <TableCell align="right">Breakeven</TableCell>
          </TableRow></TableHead>
          <TableBody>{roth.candidates.map(candidate =>
            <TableRow key={candidate.label} selected={candidate.label === roth.recommended?.label}>
              <TableCell>{candidate.label}{candidate.label === roth.recommended?.label ? ' \u2605' : ''}</TableCell>
              <TableCell align="right">{money(candidate.annual_conversion)}</TableCell>
              <TableCell align="right">{money(candidate.total_converted)}</TableCell>
              <TableCell align="right">{money(candidate.lifetime_tax_delta)}</TableCell>
              <TableCell align="right">{money(candidate.ending_after_tax_delta)}</TableCell>
              <TableCell align="right">{candidate.breakeven_year ?? '—'}</TableCell>
            </TableRow>)}</TableBody>
        </Table>}
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
          After-tax wealth values remaining tax-deferred balances at the heir rate
          ({Number(roth.heir_tax_rate) * 100}%); deltas are versus the no-conversion baseline.
        </Typography>
      </Box>}
    </CardContent></Card>

    <Card sx={{ mt: 2.5 }}><CardContent>
      <Typography variant="h6">Compare scenarios</Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>Side-by-side projections with ending assets, lifetime taxes, and shortfall deltas.</Typography>
      <Stack direction="row" sx={{ gap: 2, alignItems: 'center', flexWrap: 'wrap', mb: 2 }}>
        <FormControl size="small" sx={{ minWidth: 320 }}>
          <InputLabel>Scenarios (pick 2+)</InputLabel>
          <Select multiple value={compareIds} label="Scenarios (pick 2+)"
            onChange={e => setCompareIds(typeof e.target.value === 'string' ? e.target.value.split(',') : e.target.value)}
            renderValue={ids => (ids as string[]).map(id => scenarios.find(s => s.id === id)?.name || id).join(' · ')}>
            {scenarios.map(item => <MenuItem key={item.id} value={item.id}>{item.name}</MenuItem>)}
          </Select>
        </FormControl>
        <Button variant="contained" onClick={runCompare} disabled={compareIds.length < 2 || comparing}>{comparing ? 'Comparing…' : 'Compare'}</Button>
      </Stack>
      {comparison.length > 0 && <>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={compareChart}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="year" /><YAxis tickFormatter={v => money(v, true)} />
            <Tooltip formatter={v => money(v)} /><Legend />
            {comparison.map((item, index) =>
              <Line key={item.scenario_id} dataKey={item.name} stroke={COMPARE_COLORS[index % COMPARE_COLORS.length]} strokeWidth={3} dot={false} />)}
          </LineChart>
        </ResponsiveContainer>
        <Table size="small" sx={{ mt: 2 }}>
          <TableHead><TableRow><TableCell>Scenario</TableCell><TableCell align="right">Ending assets</TableCell><TableCell align="right">Lifetime taxes</TableCell><TableCell align="right">First shortfall</TableCell></TableRow></TableHead>
          <TableBody>{comparison.map(item =>
            <TableRow key={item.scenario_id}>
              <TableCell>{item.name}</TableCell>
              <TableCell align="right">{money(item.ending_net_worth)}</TableCell>
              <TableCell align="right">{money(item.lifetime_taxes)}</TableCell>
              <TableCell align="right">{item.first_shortfall_year
                ? <Chip size="small" color="warning" label={item.first_shortfall_year} />
                : <Chip size="small" color="success" label="None" />}</TableCell>
            </TableRow>)}</TableBody>
        </Table>
      </>}
    </CardContent></Card>
  </Box>;
}
