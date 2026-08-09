import { useState } from 'react';
import {
  Alert, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Stack,
  Table, TableBody, TableCell, TableHead, TableRow, Typography,
} from '@mui/material';
import { planningApi, type SyncActualsResult } from '../services/planningApi';

const money = (value: unknown) => new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD', maximumFractionDigits: 0,
}).format(Number(value || 0));

const STATUS_LABEL: Record<string, { label: string; color: 'success' | 'warning' | 'error' | 'default' }> = {
  on_track: { label: 'On track', color: 'success' },
  ahead: { label: 'Ahead of plan', color: 'success' },
  behind: { label: 'Behind plan', color: 'error' },
  unknown: { label: 'Unknown', color: 'default' },
};

type Props = {
  open: boolean;
  householdId: string;
  onClose: () => void;
  onApplied: () => void;
  onError: (message: string) => void;
};

/** Plan-vs-actual: refresh custodial values from the warehouse and show drift. */
export default function SyncActualsDialog({ open, householdId, onClose, onApplied, onError }: Props) {
  const [result, setResult] = useState<SyncActualsResult | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(apply: boolean) {
    if (!householdId || busy) return;
    try {
      setBusy(true);
      const next = await planningApi.syncActuals(householdId, apply);
      setResult(next);
      if (next.applied) onApplied();
    } catch (e) { onError(e instanceof Error ? e.message : 'Unable to sync actuals'); }
    finally { setBusy(false); }
  }

  function close() {
    setResult(null);
    onClose();
  }

  const drift = result ? STATUS_LABEL[result.drift.status] || STATUS_LABEL.unknown : null;

  return <Dialog open={open} onClose={() => { if (!busy) close(); }} fullWidth maxWidth="md">
    <DialogTitle>Plan vs actual</DialogTitle>
    <DialogContent>
      <Stack sx={{ gap: 2, mt: 1 }}>
        <Typography color="text.secondary">
          Re-pulls custodial account values from the warehouse and places this household
          against its projected trajectory. Advisor planning inputs are never changed.
        </Typography>
        {!result && <Button variant="contained" onClick={() => run(false)} disabled={busy}>
          {busy ? 'Checking…' : 'Check current values'}
        </Button>}
        {result && drift && <>
          <Stack direction="row" sx={{ gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
            <Chip color={drift.color} label={drift.label} />
            {result.drift.projected_portfolio && <Typography variant="body2" color="text.secondary">
              Actual {money(result.drift.actual_portfolio)} vs projected {money(result.drift.projected_portfolio)} for {result.drift.year}
            </Typography>}
          </Stack>
          {result.drift.status === 'behind' && !result.applied &&
            <Alert severity="warning">An advisor alert was created for this household.</Alert>}
          {result.applied && <Alert severity="success">Fresh warehouse values were applied to the plan copy.</Alert>}
          {result.warnings.length > 0 && <Alert severity="info">{result.warnings.join(' ')}</Alert>}
          <Table size="small">
            <TableHead><TableRow>
              <TableCell>Account</TableCell><TableCell align="right">Plan</TableCell>
              <TableCell align="right">Actual</TableCell><TableCell align="right">Δ</TableCell>
            </TableRow></TableHead>
            <TableBody>
              {result.diff.matched.map(row => <TableRow key={`m-${row.name}`}>
                <TableCell>{row.name}</TableCell>
                <TableCell align="right">{money(row.plan_value)}</TableCell>
                <TableCell align="right">{money(row.actual_value)}</TableCell>
                <TableCell align="right">{money(row.delta)}</TableCell>
              </TableRow>)}
              {result.diff.added.map(row => <TableRow key={`a-${row.name}`}>
                <TableCell>{row.name} <Chip size="small" label="new" /></TableCell>
                <TableCell align="right">—</TableCell>
                <TableCell align="right">{money(row.actual_value)}</TableCell>
                <TableCell align="right">{money(row.actual_value)}</TableCell>
              </TableRow>)}
              {result.diff.removed.map(row => <TableRow key={`r-${row.name}`}>
                <TableCell>{row.name} <Chip size="small" color="warning" label="closed" /></TableCell>
                <TableCell align="right">{money(row.plan_value)}</TableCell>
                <TableCell align="right">—</TableCell>
                <TableCell align="right">{money(-Number(row.plan_value))}</TableCell>
              </TableRow>)}
              <TableRow>
                <TableCell><strong>Total</strong></TableCell>
                <TableCell align="right"><strong>{money(result.diff.plan_total)}</strong></TableCell>
                <TableCell align="right"><strong>{money(result.diff.actual_total)}</strong></TableCell>
                <TableCell align="right"><strong>{money(result.diff.total_delta)}</strong></TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </>}
      </Stack>
    </DialogContent>
    <DialogActions>
      <Button onClick={close} disabled={busy}>Close</Button>
      {result && !result.applied &&
        <Button variant="contained" onClick={() => run(true)} disabled={busy}>
          {busy ? 'Applying…' : 'Apply fresh values to plan'}
        </Button>}
    </DialogActions>
  </Dialog>;
}
