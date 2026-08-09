import { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Box, Card, CardContent, Typography } from '@mui/material';
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from 'recharts';
import { ChartContainer, ChartLegend, ChartTooltip } from '../components/ui/chart';
import { planningApi } from '../services/planningApi';
import { Kpi, chartColors, money } from './shared';

interface Props {
  scenario: string;
  estate: Record<string, unknown> | null;
  onError: (message: string) => void;
}

export default function EstateTab({ scenario, estate, onError }: Props) {
  const [taxYears, setTaxYears] = useState<Array<{ year: number; gross_estate: string; federal_estate_tax: string }>>([]);

  const load = useCallback(async () => {
    try { setTaxYears((await planningApi.estateTaxProjection(scenario)).years); }
    catch (e) { onError(e instanceof Error ? e.message : 'Estate tax projection failed'); }
  }, [scenario, onError]);

  useEffect(() => { setTaxYears([]); void load(); }, [load]);

  const taxChart = useMemo(() => taxYears.map(row => ({
    year: row.year,
    'Gross estate': Number(row.gross_estate),
    'Federal estate tax': Number(row.federal_estate_tax),
  })), [taxYears]);

  return <Box className="plan-panel">
    <Box className="plan-metrics" sx={{ gridTemplateColumns: 'repeat(4, minmax(0,1fr))' }}>
      <Kpi label="Gross estate" value={money(estate?.gross_estate)} />
      <Kpi label="Liquidity need" value={money(estate?.liquidity_need)} />
      <Kpi label="Federal estate tax" value={money(estate?.federal_estate_tax)} tone={Number(estate?.federal_estate_tax || 0) > 0 ? 'loss' : undefined} />
      <Kpi label="Net to heirs" value={money(estate?.net_to_heirs)} tone="gain" />
    </Box>
    <Card><CardContent>
      <Typography variant="h6">Estate distribution and liquidity</Typography>
      <Typography color="text.secondary">Contract beneficiaries, titling, marital transfers, estate costs, taxes, and forced-sale risk are evaluated in order.</Typography>
      {Number(estate?.liquidity_shortfall || 0) > 0 &&
        <Alert severity="warning" sx={{ mt: 2 }}>Projected estate liquidity shortfall: {money(estate?.liquidity_shortfall)}</Alert>}
    </CardContent></Card>
    {taxChart.length > 0 && <Card sx={{ mt: 2.5 }}><CardContent>
      <Typography variant="h6">Estate tax exposure over time</Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>Projected gross estate and federal estate tax if death occurs in each plan year.</Typography>
      <ChartContainer width="100%" height={320}>
        <LineChart data={taxChart}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="year" /><YAxis tickFormatter={v => money(v, true)} />
          <ChartTooltip formatter={v => money(v)} /><ChartLegend />
          <Line dataKey="Gross estate" stroke={chartColors.nightBlue} strokeWidth={3} dot={false} />
          <Line dataKey="Federal estate tax" stroke={chartColors.pumpkin} strokeWidth={3} dot={false} />
        </LineChart>
      </ChartContainer>
    </CardContent></Card>}
  </Box>;
}
