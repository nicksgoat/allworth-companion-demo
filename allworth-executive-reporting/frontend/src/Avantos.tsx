import { useEffect, useMemo, useState } from 'react';
import {
  Alert, AppBar, Box, Card, CardContent, Chip, CircularProgress, Container,
  LinearProgress, Stack, Table, TableBody, TableCell, TableHead, TableRow,
  TextField, Toolbar, Typography,
} from '@mui/material';
import SideNav from './components/SideNav';
import './Avantos.css';

type CockpitRow = {
  household_id: string; name: string; source: string; total_assets: string;
  ending_net_worth: string; first_shortfall_year: number | null;
  health_score: number; health_band: 'healthy' | 'watch' | 'at_risk';
  goals_total: number; goals_funded: number; open_alerts: number; open_tasks: number;
  drift_flagged: boolean; last_actuals_sync: string | null;
  publication_status: string; published_at: string | null;
  data_quality_warnings: number;
};

type Cockpit = {
  summary: {
    households: number; total_assets: string; at_risk: number; watch: number;
    healthy: number; drift_flagged: number; unpublished: number;
    open_alerts: number; open_tasks: number;
  };
  households: CockpitRow[];
};

const money = (value: unknown, compact = true) => new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD', maximumFractionDigits: 0, notation: compact ? 'compact' : 'standard',
}).format(Number(value || 0));

const BAND: Record<CockpitRow['health_band'], { label: string; color: 'success' | 'warning' | 'error' }> = {
  healthy: { label: 'Healthy', color: 'success' },
  watch: { label: 'Watch', color: 'warning' },
  at_risk: { label: 'At risk', color: 'error' },
};

function Tile({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return <Card className="av-tile"><CardContent>
    <Typography className="av-tile__label">{label}</Typography>
    <Typography className="av-tile__value" color={tone}>{value}</Typography>
  </CardContent></Card>;
}

export default function Avantos() {
  const [cockpit, setCockpit] = useState<Cockpit | null>(null);
  const [crm, setCrm] = useState<{ open_opportunities: number; open_pipeline_paum: number } | null>(null);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('');

  useEffect(() => {
    fetch('/api/avantos/cockpit', { headers: { 'Content-Type': 'application/json' } })
      .then(async response => {
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
        setCockpit(await response.json());
      })
      .catch(e => setError(e instanceof Error ? e.message : 'Unable to load cockpit'));
    // CRM pipeline context — optional; the cockpit degrades gracefully if the
    // CRM module or the warehouse is unavailable.
    fetch('/api/crm/summary', { headers: { 'Content-Type': 'application/json' } })
      .then(async response => {
        if (!response.ok) return;
        const body = await response.json();
        if (body?.success && body.data) setCrm(body.data);
      })
      .catch(() => undefined);
  }, []);

  const rows = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return (cockpit?.households || []).filter(row =>
      !needle || row.name.toLowerCase().includes(needle));
  }, [cockpit, filter]);

  return <div className="has-sidenav">
    <SideNav />
    <Box className="av-shell">
    <AppBar position="static" elevation={0} className="av-header"><Toolbar>
      <Box sx={{ flex: 1 }}>
        <Typography className="av-brand">AVANTOS</Typography>
        <Typography className="av-product">Advisor operating console</Typography>
      </Box>
      <Chip label="Planning book of business" className="av-chip" />
    </Toolbar></AppBar>
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {error && <Alert severity="error" onClose={() => setError('')} sx={{ mb: 2 }}>{error}</Alert>}
      {!cockpit && !error && <Box className="av-loading"><CircularProgress /></Box>}
      {cockpit && <>
        <Box className="av-tiles">
          <Tile label="Households" value={String(cockpit.summary.households)} />
          <Tile label="Book assets" value={money(cockpit.summary.total_assets)} />
          <Tile label="At risk" value={String(cockpit.summary.at_risk)}
            tone={cockpit.summary.at_risk ? 'error.main' : 'success.main'} />
          <Tile label="Drift flagged" value={String(cockpit.summary.drift_flagged)}
            tone={cockpit.summary.drift_flagged ? 'warning.main' : 'success.main'} />
          <Tile label="Unpublished plans" value={String(cockpit.summary.unpublished)} />
          <Tile label="Open work items"
            value={String(cockpit.summary.open_alerts + cockpit.summary.open_tasks)} />
          {crm && <Tile label="CRM open opportunities" value={String(crm.open_opportunities)} />}
          {crm && <Tile label="CRM pipeline PAUM" value={money(crm.open_pipeline_paum)} />}
        </Box>
        <Card className="av-table-card"><CardContent>
          <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
            <Box>
              <Typography variant="h6">Households by need</Typography>
              <Typography color="text.secondary" variant="body2">
                At-risk plans first, then drift, then open work. Click through to Financial Planning to act.
              </Typography>
            </Box>
            <TextField size="small" label="Filter households" value={filter}
              onChange={e => setFilter(e.target.value)} />
          </Stack>
          <Table size="small">
            <TableHead><TableRow>
              <TableCell>Household</TableCell>
              <TableCell>Health</TableCell>
              <TableCell align="right">Assets</TableCell>
              <TableCell align="right">Projected ending</TableCell>
              <TableCell align="right">Shortfall</TableCell>
              <TableCell align="right">Goals</TableCell>
              <TableCell align="right">Work items</TableCell>
              <TableCell>Plan status</TableCell>
              <TableCell>Flags</TableCell>
            </TableRow></TableHead>
            <TableBody>{rows.map(row => (
              <TableRow key={row.household_id} hover className="av-row"
                onClick={() => { window.location.href = '/planning'; }}>
                <TableCell>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>{row.name}</Typography>
                  <Typography variant="caption" color="text.secondary">{row.source}</Typography>
                </TableCell>
                <TableCell>
                  <Stack direction="row" sx={{ gap: 1, alignItems: 'center' }}>
                    <Chip size="small" color={BAND[row.health_band].color}
                      label={`${row.health_score}`} />
                    <Box sx={{ width: 64 }}>
                      <LinearProgress variant="determinate" value={row.health_score}
                        color={BAND[row.health_band].color}
                        sx={{ height: 5, borderRadius: 3 }} />
                    </Box>
                  </Stack>
                </TableCell>
                <TableCell align="right">{money(row.total_assets)}</TableCell>
                <TableCell align="right">{money(row.ending_net_worth)}</TableCell>
                <TableCell align="right">{row.first_shortfall_year ?? '—'}</TableCell>
                <TableCell align="right">
                  {row.goals_total ? `${row.goals_funded}/${row.goals_total}` : '—'}
                </TableCell>
                <TableCell align="right">{row.open_alerts + row.open_tasks || '—'}</TableCell>
                <TableCell>
                  <Chip size="small" variant="outlined"
                    color={row.publication_status === 'published' ? 'success' : 'default'}
                    label={row.publication_status} />
                </TableCell>
                <TableCell>
                  <Stack direction="row" sx={{ gap: 0.5, flexWrap: 'wrap' }}>
                    {row.drift_flagged && <Chip size="small" color="warning" label="drift" />}
                    {row.data_quality_warnings > 0 &&
                      <Chip size="small" variant="outlined" label={`${row.data_quality_warnings} DQ`} />}
                    {row.last_actuals_sync &&
                      <Chip size="small" variant="outlined" label="synced" />}
                    {row.source === 'datawarehouse' &&
                      <Chip size="small" variant="outlined" label="CRM" clickable
                        onClick={event => { event.stopPropagation();
                          window.location.href = `/crm?q=${encodeURIComponent(row.name)}`; }} />}
                  </Stack>
                </TableCell>
              </TableRow>))}
            </TableBody>
          </Table>
          {rows.length === 0 && <Alert severity="info" sx={{ mt: 2 }}>
            No planning households yet. Import a household in Financial Planning and it will appear here.
          </Alert>}
        </CardContent></Card>
      </>}
    </Container>
    </Box>
  </div>;
}
