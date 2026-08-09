import { useMemo } from 'react';
import { Alert, Button, Card, CardContent, Box, LinearProgress, Typography } from '@mui/material';
import { Area, CartesianGrid, ComposedChart, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { MonteCarloInputs, MonteCarloResult } from '../services/planningApi';
import { Kpi, chartColors, money, pct } from './shared';

interface Props {
  mcInputs: MonteCarloInputs | null;
  mcResult: MonteCarloResult | null;
  mcRunning: boolean;
  onRun: () => void;
}

export default function MonteCarloTab({ mcInputs, mcResult, mcRunning, onRun }: Props) {
  const bands = useMemo(() => (mcResult?.net_worth_bands || []).map(band => ({
    year: band.year,
    outer: [Number(band.p5), Number(band.p95)] as [number, number],
    inner: [Number(band.p25), Number(band.p75)] as [number, number],
    median: Number(band.p50),
  })), [mcResult]);

  const successByAge = useMemo(() => Object.entries(mcResult?.success_by_age || {})
    .map(([age, probability]) => ({ age: Number(age), probability: Number(probability) * 100 }))
    .sort((a, b) => a.age - b.age), [mcResult]);

  const percentiles = mcResult?.ending_value_percentiles || {};

  return <Box className="plan-panel">
    <div className="plan-toolbar">
      <Box>
        <Typography variant="h6">Monte Carlo simulation</Typography>
        <Typography color="text.secondary">
          {mcResult ? `${mcResult.n_trials.toLocaleString()} trials · seed ${mcResult.seed}` : mcInputs?.ready ? 'Inputs ready — run the simulation to see outcome bands.' : 'Inputs needed — complete holdings and capital-market assumptions in Planning Inputs.'}
        </Typography>
      </Box>
      <Button variant="contained" onClick={onRun} disabled={!mcInputs?.ready || mcRunning}>
        {mcRunning ? 'Simulating…' : mcResult ? 'Re-run simulation' : 'Run simulation'}
      </Button>
    </div>
    {mcRunning && <LinearProgress sx={{ mb: 2 }} />}
    {!mcResult && !mcRunning && mcInputs && !mcInputs.ready &&
      <Alert severity="warning">Missing required inputs: {mcInputs.missing_required_inputs.join(', ') || 'unknown'}</Alert>}
    {mcResult && <>
      <Box className="plan-metrics">
        <Kpi label="Probability of success" value={pct(mcResult.probability_of_success)} tone={mcResult.probability_of_success >= 0.8 ? 'gain' : 'loss'} />
        <Kpi label="Median ending value" value={money(percentiles.p50, true)} />
        <Kpi label="Downside (5th pct)" value={money(percentiles.p5, true)} tone={Number(percentiles.p5) <= 0 ? 'loss' : undefined} />
        <Kpi label="Upside (95th pct)" value={money(percentiles.p95, true)} />
        <Kpi label="Trials" value={mcResult.n_trials.toLocaleString()} />
      </Box>
      <Card><CardContent>
        <Typography variant="h6">Net worth outcome bands</Typography>
        <Typography color="text.secondary" sx={{ mb: 2 }}>5th–95th percentile fan with interquartile band and median path</Typography>
        <ResponsiveContainer width="100%" height={380}>
          <ComposedChart data={bands}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="year" />
            <YAxis tickFormatter={v => money(v, true)} />
            <Tooltip formatter={(value: unknown) => Array.isArray(value) ? `${money(value[0])} – ${money(value[1])}` : money(value)} />
            <Area dataKey="outer" name="5th–95th" stroke="none" fill={chartColors.sky} fillOpacity={0.16} />
            <Area dataKey="inner" name="25th–75th" stroke="none" fill={chartColors.sky} fillOpacity={0.28} />
            <Line dataKey="median" name="Median" stroke={chartColors.nightBlue} strokeWidth={3} dot={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </CardContent></Card>
      <Card sx={{ mt: 2.5 }}><CardContent>
        <Typography variant="h6">Success by age</Typography>
        <Typography color="text.secondary" sx={{ mb: 2 }}>Share of trials still funded at each client age</Typography>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={successByAge}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="age" />
            <YAxis domain={[0, 100]} tickFormatter={v => `${v}%`} />
            <Tooltip formatter={(value: unknown) => `${Number(value).toFixed(1)}%`} />
            <Line dataKey="probability" name="Funded" stroke={chartColors.evergreen} strokeWidth={3} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </CardContent></Card>
    </>}
  </Box>;
}
