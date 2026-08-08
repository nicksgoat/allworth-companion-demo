import { useState } from 'react';
import { Alert, Box, Button, Card, CardContent, Stack, Table, TableBody, TableCell, TableHead, TableRow, TextField, Typography } from '@mui/material';
import { planningApi } from '../services/planningApi';
import { money, pct } from './shared';

export default function ToolsTab({ onError }: { onError: (message: string) => void }) {
  const [clientPia, setClientPia] = useState('2800');
  const [spousePia, setSpousePia] = useState('1900');
  const [ssResult, setSsResult] = useState<{ client_claim_age: number; spouse_claim_age: number; expected_lifetime_benefit: string } | null>(null);
  const [ssRunning, setSsRunning] = useState(false);

  const [iraBalance, setIraBalance] = useState('500000');
  const [iraResult, setIraResult] = useState<Record<string, string[]> | null>(null);
  const [iraRunning, setIraRunning] = useState(false);

  const [costBasis, setCostBasis] = useState('100000');
  const [marketValue, setMarketValue] = useState('400000');
  const [ordinaryRate, setOrdinaryRate] = useState('0.35');
  const [ltcgRate, setLtcgRate] = useState('0.15');
  const [nuaResult, setNuaResult] = useState<Record<string, string> | null>(null);
  const [nuaRunning, setNuaRunning] = useState(false);

  async function runSs() {
    setSsRunning(true);
    try { setSsResult(await planningApi.socialSecurityOptimizer(clientPia, spousePia)); }
    catch (e) { onError(e instanceof Error ? e.message : 'Social Security optimizer failed'); }
    finally { setSsRunning(false); }
  }

  async function runIra() {
    setIraRunning(true);
    try { setIraResult(await planningApi.inheritedIra(iraBalance)); }
    catch (e) { onError(e instanceof Error ? e.message : 'Inherited IRA calculator failed'); }
    finally { setIraRunning(false); }
  }

  async function runNua() {
    setNuaRunning(true);
    try { setNuaResult(await planningApi.nua(costBasis, marketValue, ordinaryRate, ltcgRate)); }
    catch (e) { onError(e instanceof Error ? e.message : 'NUA analysis failed'); }
    finally { setNuaRunning(false); }
  }

  const iraYears = iraResult ? Math.max(...Object.values(iraResult).map(values => values.length)) : 0;

  return <Box className="plan-panel">
    <Box className="plan-decision" sx={{ gridTemplateColumns: { md: 'repeat(2, minmax(0,1fr))' } }}>
      <Card><CardContent>
        <Typography variant="h6">Social Security optimizer</Typography>
        <Typography color="text.secondary" sx={{ mb: 2 }}>Finds the claiming ages that maximize expected lifetime household benefits.</Typography>
        <Stack sx={{ gap: 2 }}>
          <TextField size="small" label="Client PIA (monthly at FRA)" type="number" value={clientPia} onChange={e => setClientPia(e.target.value)} />
          <TextField size="small" label="Spouse PIA (monthly at FRA)" type="number" value={spousePia} onChange={e => setSpousePia(e.target.value)} />
          <Button variant="contained" onClick={runSs} disabled={ssRunning}>{ssRunning ? 'Optimizing…' : 'Optimize claiming ages'}</Button>
          {ssResult && <Alert severity="success">
            Claim at <strong>{ssResult.client_claim_age}</strong> (client) and <strong>{ssResult.spouse_claim_age}</strong> (spouse)
            — expected lifetime benefit {money(ssResult.expected_lifetime_benefit)}.
          </Alert>}
        </Stack>
      </CardContent></Card>
      <Card><CardContent>
        <Typography variant="h6">NUA analysis</Typography>
        <Typography color="text.secondary" sx={{ mb: 2 }}>Net unrealized appreciation: lump-sum distribution vs. rolling employer stock into an IRA.</Typography>
        <Stack sx={{ gap: 2 }}>
          <Stack direction="row" sx={{ gap: 2 }}>
            <TextField size="small" fullWidth label="Cost basis" type="number" value={costBasis} onChange={e => setCostBasis(e.target.value)} />
            <TextField size="small" fullWidth label="Market value" type="number" value={marketValue} onChange={e => setMarketValue(e.target.value)} />
          </Stack>
          <Stack direction="row" sx={{ gap: 2 }}>
            <TextField size="small" fullWidth label="Ordinary rate" type="number" value={ordinaryRate} onChange={e => setOrdinaryRate(e.target.value)} slotProps={{ htmlInput: { step: 0.01, min: 0, max: 1 } }} />
            <TextField size="small" fullWidth label="LTCG rate" type="number" value={ltcgRate} onChange={e => setLtcgRate(e.target.value)} slotProps={{ htmlInput: { step: 0.01, min: 0, max: 1 } }} />
          </Stack>
          <Button variant="contained" onClick={runNua} disabled={nuaRunning}>{nuaRunning ? 'Analyzing…' : 'Analyze NUA'}</Button>
          {nuaResult && <Table size="small">
            <TableBody>{Object.entries(nuaResult).map(([key, value]) =>
              <TableRow key={key}>
                <TableCell sx={{ textTransform: 'capitalize' }}>{key.replaceAll('_', ' ')}</TableCell>
                <TableCell align="right">{key.includes('rate') ? pct(value, 1) : money(value)}</TableCell>
              </TableRow>)}</TableBody>
          </Table>}
        </Stack>
      </CardContent></Card>
    </Box>
    <Card sx={{ mt: 2.5 }}><CardContent>
      <Typography variant="h6">Inherited IRA distributions</Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>10-year rule payout schedules under different distribution strategies.</Typography>
      <Stack direction="row" sx={{ gap: 2, alignItems: 'center', mb: 2 }}>
        <TextField size="small" label="Inherited balance" type="number" value={iraBalance} onChange={e => setIraBalance(e.target.value)} />
        <Button variant="contained" onClick={runIra} disabled={iraRunning}>{iraRunning ? 'Calculating…' : 'Calculate schedules'}</Button>
      </Stack>
      {iraResult && <Table size="small">
        <TableHead><TableRow>
          <TableCell>Year</TableCell>
          {Object.keys(iraResult).map(strategy => <TableCell key={strategy} align="right" sx={{ textTransform: 'capitalize' }}>{strategy.replaceAll('_', ' ')}</TableCell>)}
        </TableRow></TableHead>
        <TableBody>{Array.from({ length: iraYears }, (_, index) =>
          <TableRow key={index}>
            <TableCell>{index + 1}</TableCell>
            {Object.keys(iraResult).map(strategy =>
              <TableCell key={strategy} align="right">{iraResult[strategy][index] ? money(iraResult[strategy][index]) : '—'}</TableCell>)}
          </TableRow>)}</TableBody>
      </Table>}
    </CardContent></Card>
  </Box>;
}
