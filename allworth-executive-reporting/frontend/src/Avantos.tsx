import { useEffect, useMemo, useState } from 'react';
import {
  Alert, Box, Chip, CircularProgress,
  Stack, Table, TableBody, TableCell, TableHead, TableRow,
  TextField, Typography,
} from '@mui/material';
import { Bar, BarChart, XAxis, YAxis } from 'recharts';
import { ChartContainer, ChartTooltip } from './components/ui/chart';
import { ToolMetric, ToolMetricGrid, ToolPage, ToolPanel } from './components/ToolPage';
import { chartTheme } from './theme';
import './Avantos.css';
import { useWorkspace } from './components/WorkspaceContext';
import { householdHref, type HouseholdContext } from './services/workspace';

const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';

type CockpitRow = {
  household_id: string; name: string; source: string; total_assets: string;
  ending_net_worth: string; first_shortfall_year: number | null;
  health_score: number; health_band: 'healthy' | 'watch' | 'at_risk';
  goals_total: number; goals_funded: number; open_alerts: number; open_tasks: number;
  drift_flagged: boolean; last_actuals_sync: string | null;
  publication_status: string; published_at: string | null;
  data_quality_warnings: number;
  source_id?: string | null; avhhid?: string | null; advisor_id?: string | null; crm_lead_id?: string | null;
};

type Cockpit = {
  summary: {
    households: number; total_assets: string; at_risk: number; watch: number;
    healthy: number; drift_flagged: number; unpublished: number;
    open_alerts: number; open_tasks: number;
  };
  households: CockpitRow[];
};

const DEMO_COCKPIT: Cockpit = {
  summary: {
    households: 6, total_assets: '96300000', at_risk: 2, watch: 2,
    healthy: 2, drift_flagged: 2, unpublished: 2, open_alerts: 4, open_tasks: 7,
  },
  households: [
    { household_id: 'hh-201', name: 'Evergreen Family', source: 'datawarehouse', total_assets: '12400000', ending_net_worth: '1800000', first_shortfall_year: 2041, health_score: 42, health_band: 'at_risk', goals_total: 4, goals_funded: 1, open_alerts: 2, open_tasks: 1, drift_flagged: true, last_actuals_sync: '2026-08-06', publication_status: 'draft', published_at: null, data_quality_warnings: 1 },
    { household_id: 'hh-204', name: 'Stonebridge Family', source: 'datawarehouse', total_assets: '8900000', ending_net_worth: '2400000', first_shortfall_year: 2048, health_score: 54, health_band: 'at_risk', goals_total: 3, goals_funded: 1, open_alerts: 1, open_tasks: 2, drift_flagged: true, last_actuals_sync: '2026-08-05', publication_status: 'draft', published_at: null, data_quality_warnings: 0 },
    { household_id: 'hh-202', name: 'Northstar Household', source: 'planning', total_assets: '17800000', ending_net_worth: '9600000', first_shortfall_year: null, health_score: 68, health_band: 'watch', goals_total: 4, goals_funded: 3, open_alerts: 1, open_tasks: 2, drift_flagged: false, last_actuals_sync: '2026-08-07', publication_status: 'published', published_at: '2026-08-01', data_quality_warnings: 0 },
    { household_id: 'hh-205', name: 'Summit Ridge Trust', source: 'planning', total_assets: '14100000', ending_net_worth: '11800000', first_shortfall_year: null, health_score: 76, health_band: 'watch', goals_total: 3, goals_funded: 3, open_alerts: 0, open_tasks: 1, drift_flagged: false, last_actuals_sync: '2026-08-07', publication_status: 'published', published_at: '2026-07-29', data_quality_warnings: 0 },
    { household_id: 'hh-203', name: 'Harbor Ridge Household', source: 'datawarehouse', total_assets: '21500000', ending_net_worth: '24600000', first_shortfall_year: null, health_score: 91, health_band: 'healthy', goals_total: 5, goals_funded: 5, open_alerts: 0, open_tasks: 1, drift_flagged: false, last_actuals_sync: '2026-08-08', publication_status: 'published', published_at: '2026-08-03', data_quality_warnings: 0 },
    { household_id: 'hh-206', name: 'Cedar Grove Family', source: 'planning', total_assets: '21600000', ending_net_worth: '28700000', first_shortfall_year: null, health_score: 94, health_band: 'healthy', goals_total: 4, goals_funded: 4, open_alerts: 0, open_tasks: 0, drift_flagged: false, last_actuals_sync: '2026-08-08', publication_status: 'published', published_at: '2026-08-02', data_quality_warnings: 0 },
  ],
};

const money = (value: unknown, compact = true) => new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD', maximumFractionDigits: 0, notation: compact ? 'compact' : 'standard',
}).format(Number(value || 0));

const BAND: Record<CockpitRow['health_band'], { label: string; color: 'success' | 'warning' | 'error' }> = {
  healthy: { label: 'Healthy', color: 'success' },
  watch: { label: 'Watch', color: 'warning' },
  at_risk: { label: 'At risk', color: 'error' },
};

function contextForRow(row: CockpitRow): HouseholdContext {
  return {
    planning_household_id: row.household_id,
    crm_lead_id: row.crm_lead_id ?? null,
    salesforce_household_id: row.source_id ?? null,
    avhhid: row.avhhid ?? null,
    name: row.name,
    advisor_id: row.advisor_id ?? null,
    advisor_name: null,
    aum: Number(row.total_assets),
    plan_status: row.publication_status === 'published' ? 'published' : 'draft',
    last_actuals_sync: row.last_actuals_sync,
    freshness: row.last_actuals_sync ? 'available' : 'unknown',
    data_quality_warnings: row.data_quality_warnings,
    data_quality_state: row.data_quality_warnings ? 'warning' : 'healthy',
  };
}

function HealthScoreChart({ score, band }: { score: number; band: CockpitRow['health_band'] }) {
  const fill = band === 'healthy' ? chartTheme.positive : band === 'watch' ? chartTheme.neutral : chartTheme.warning;
  return (
    <ChartContainer width={72} height={16} aria-label={`Planning health score ${score} out of 100`}>
      <BarChart data={[{ label: 'Health', score, remaining: Math.max(0, 100 - score) }]} layout="vertical" margin={{ top: 3, right: 0, bottom: 3, left: 0 }}>
        <XAxis type="number" domain={[0, 100]} hide />
        <YAxis type="category" dataKey="label" hide />
        <ChartTooltip formatter={(value, name) => [`${Number(value).toFixed(0)}`, String(name)]} />
        <Bar dataKey="score" name="Health score" stackId="health" fill={fill} radius={[3, 0, 0, 3]} isAnimationActive={false} />
        <Bar dataKey="remaining" name="Remaining" stackId="health" fill={chartTheme.grid} radius={[0, 3, 3, 0]} isAnimationActive={false} />
      </BarChart>
    </ChartContainer>
  );
}

export default function Avantos() {
  const { me } = useWorkspace();
  const [cockpit, setCockpit] = useState<Cockpit | null>(null);
  const [crm, setCrm] = useState<{ open_opportunities: number; open_pipeline_paum: number } | null>(null);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('');

  useEffect(() => {
    if (DEMO_MODE) {
      setCockpit(DEMO_COCKPIT);
      setCrm({ open_opportunities: 14, open_pipeline_paum: 68400000 });
      return;
    }
    const advisorQuery = me?.assignment.type === 'advisor' && me.advisor?.advisor_id
      ? `?advisor_id=${encodeURIComponent(me.advisor.advisor_id)}` : '';
    fetch(`/api/avantos/cockpit${advisorQuery}`, { headers: { 'Content-Type': 'application/json' } })
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
  }, [me?.assignment.type, me?.advisor?.advisor_id]);

  const rows = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return (cockpit?.households || []).filter(row =>
      !needle || row.name.toLowerCase().includes(needle));
  }, [cockpit, filter]);

  return <ToolPage
    eyebrow="Advisor console"
    title="Avantos"
    description="Prioritize households by planning health, drift, open work, and pipeline context."
    width="full"
  >
      {error && <Alert severity="error" onClose={() => setError('')} sx={{ mb: 2 }}>{error}</Alert>}
      {!cockpit && !error && <Box className="av-loading"><CircularProgress /></Box>}
      {cockpit && <>
        <ToolMetricGrid>
          <ToolMetric label="Households" value={String(cockpit.summary.households)} />
          <ToolMetric label="Book assets" value={money(cockpit.summary.total_assets)} />
          <ToolMetric label="At risk" value={String(cockpit.summary.at_risk)}
            tone={cockpit.summary.at_risk ? 'critical' : 'positive'} />
          <ToolMetric label="Drift flagged" value={String(cockpit.summary.drift_flagged)}
            tone={cockpit.summary.drift_flagged ? 'warning' : 'positive'} />
          <ToolMetric label="Unpublished plans" value={String(cockpit.summary.unpublished)} />
          <ToolMetric label="Open work items"
            value={String(cockpit.summary.open_alerts + cockpit.summary.open_tasks)} />
          {crm && <ToolMetric label="CRM open opportunities" value={String(crm.open_opportunities)} />}
          {crm && <ToolMetric label="CRM pipeline PAUM" value={money(crm.open_pipeline_paum)} />}
        </ToolMetricGrid>
        <ToolPanel
          title="Households by need"
          description="At-risk plans first, then drift, then open work. Click through to Financial Planning to act."
          actions={<TextField size="small" label="Filter households" value={filter}
            onChange={e => setFilter(e.target.value)} />}
          flush
        >
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
                onClick={() => { window.location.href = householdHref('/planning', contextForRow(row)); }}>
                <TableCell>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>{row.name}</Typography>
                  <Typography variant="caption" color="text.secondary">Connected household</Typography>
                </TableCell>
                <TableCell>
                  <Stack direction="row" sx={{ gap: 1, alignItems: 'center' }}>
                    <Chip size="small" color={BAND[row.health_band].color}
                      label={`${row.health_score}`} />
                    <HealthScoreChart score={row.health_score} band={row.health_band} />
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
                    {row.crm_lead_id &&
                      <Chip size="small" variant="outlined" label="Relationship" clickable
                        onClick={event => { event.stopPropagation();
                          window.location.href = householdHref('/crm', contextForRow(row)); }} />}
                  </Stack>
                </TableCell>
              </TableRow>))}
            </TableBody>
          </Table>
          {rows.length === 0 && <Alert severity="info" sx={{ mt: 2 }}>
            No planning households yet. Import a household in Financial Planning and it will appear here.
          </Alert>}
        </ToolPanel>
      </>}
  </ToolPage>;
}
