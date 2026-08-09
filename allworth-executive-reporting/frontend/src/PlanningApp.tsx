import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert, Box, Button, Card, CardContent, Chip, CircularProgress, Container,
  Dialog, DialogActions, DialogContent, DialogTitle, Divider, FormControl,
  InputLabel, MenuItem, Select, Stack, Tab, Tabs, TextField, Typography,
} from '@mui/material';
import { ThemeProvider } from '@mui/material/styles';
import AddIcon from '@mui/icons-material/Add';
import AccountBalanceWalletOutlinedIcon from '@mui/icons-material/AccountBalanceWalletOutlined';
import CloudSyncOutlinedIcon from '@mui/icons-material/CloudSyncOutlined';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { planningApi, type Household, type MonteCarloInputs, type MonteCarloResult, type Projection, type Scenario } from './services/planningApi';
import PlanningInputs, { type PlanningFactsDraft } from './PlanningInputs';
import DecisionTab from './planning/DecisionTab';
import AssumptionsTab from './planning/AssumptionsTab';
import ClientViewTab from './planning/ClientViewTab';
import EstateTab from './planning/EstateTab';
import LifecycleTab from './planning/LifecycleTab';
import MonteCarloTab from './planning/MonteCarloTab';
import ReportsTab from './planning/ReportsTab';
import ToolsTab from './planning/ToolsTab';
import VaultTab from './planning/VaultTab';
import WorkspaceTab from './planning/WorkspaceTab';
import SyncActualsDialog from './components/SyncActualsDialog';
import { Kpi as Metric, money } from './planning/shared';
import AuthControl from './components/AuthControl';
import SideNav from './components/SideNav';
import ShareTool from './components/ShareTool';
import { colors, muiTheme } from './theme';
import './PlanningApp.css';

const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';
const DEMO_HOUSEHOLD: Household = { id: 'demo-household', name: 'Evergreen Family', people: 2, accounts: 4, source: 'datawarehouse' };
const DEMO_SCENARIO: Scenario = { id: 'demo-scenario', household_id: DEMO_HOUSEHOLD.id, name: 'Proposed Plan', overrides: [], is_recommended: true };
const DEMO_PROJECTION: Projection = {
  household_id: DEMO_HOUSEHOLD.id,
  start_year: 2026,
  rows: Array.from({ length: 25 }, (_, index) => {
    const year = 2026 + index;
    const netWorth = 8_600_000 * Math.pow(1.035, index) - Math.max(0, index - 9) * 190_000;
    return { year, client_age: 60 + index, phase: index < 6 ? 'accumulation' : 'retirement', inflows: String(index < 6 ? 410000 : 165000), outflows: String(index < 6 ? 230000 : 310000), taxes: String(index < 6 ? 92000 : 58000), investment_growth: String(netWorth * 0.045), withdrawals: String(index < 6 ? 0 : 210000), savings: String(index < 6 ? 88000 : 0), shortfall: '0', net_worth: String(Math.round(netWorth)) };
  }),
  ending_net_worth: '11240000', lifetime_taxes: '2140000', first_shortfall_year: null, warnings: [],
};
const DEMO_MC_INPUTS: MonteCarloInputs = {
  ready: true, missing_required_inputs: [], warnings: [], holdings_as_of: '2026-08-07',
  cma_version: '2026.1', cma_as_of: '2026-01-01', cma_source: 'Allworth CMA',
  portfolio_expected_return: 0.061, portfolio_volatility: 0.118, asset_classes: [], provenance: {},
};

function EmptyState({ onCreate }: { onCreate: () => void }) {
  return <Box className="plan-empty"><AccountBalanceWalletOutlinedIcon sx={{ fontSize: 54 }} />
    <Typography variant="h4">Start a financial plan</Typography>
    <Typography color="text.secondary">Import a household from the DataWarehouse or create a planning draft.</Typography>
    <Button variant="contained" startIcon={<AddIcon />} onClick={onCreate}>Create household</Button></Box>;
}

export default function PlanningApp() {
  const [households, setHouseholds] = useState<Household[]>(DEMO_MODE ? [DEMO_HOUSEHOLD] : []);
  const [selected, setSelected] = useState(DEMO_MODE ? DEMO_HOUSEHOLD.id : '');
  const [summary, setSummary] = useState<Record<string, unknown> | null>(DEMO_MODE ? { name: DEMO_HOUSEHOLD.name, source: DEMO_HOUSEHOLD.source, net_worth: '8600000' } : null);
  const [facts, setFacts] = useState<Record<string, unknown> | null>(DEMO_MODE ? { people: [{ first_name: 'Alex', last_name: 'Evergreen', retirement_age: 66 }], accounts: [{ name: 'Joint Brokerage', kind: 'taxable', value: '4200000' }], income: [{ name: 'Employment', amount: '410000' }], expenses: [{ name: 'Living expenses', amount: '230000' }], assumptions: { start_year: 2026 } } : null);
  const [scenarios, setScenarios] = useState<Scenario[]>(DEMO_MODE ? [DEMO_SCENARIO] : []);
  const [scenario, setScenario] = useState(DEMO_MODE ? DEMO_SCENARIO.id : '');
  const [projection, setProjection] = useState<Projection | null>(DEMO_MODE ? DEMO_PROJECTION : null);
  const [tab, setTab] = useState(0);
  const [loading, setLoading] = useState(!DEMO_MODE);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [birthDate, setBirthDate] = useState('1975-01-01');
  const [retirementAge, setRetirementAge] = useState('65');
  const [annualSpending, setAnnualSpending] = useState('0');
  const [applying, setApplying] = useState(false);
  const [estate, setEstate] = useState<Record<string, unknown> | null>(null);
  const [goals, setGoals] = useState<Array<Record<string, string>>>(DEMO_MODE ? [{ id: 'retirement', name: 'Retirement lifestyle', status: 'funded', funded_pct: '93', available: '4850000', target_year: '2032', target_amount: '5200000', shortfall: '350000' }] : []);
  const [reports, setReports] = useState<Array<{ id: number; name: string }>>(DEMO_MODE ? [{ id: 1, name: 'Plan summary' }] : []);
  const [warehouseId, setWarehouseId] = useState('');
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState('');
  const [mcInputs, setMcInputs] = useState<MonteCarloInputs | null>(DEMO_MODE ? DEMO_MC_INPUTS : null);
  const [mcResult, setMcResult] = useState<MonteCarloResult | null>(null);
  const [mcRunning, setMcRunning] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState('');
  const [deleteReason, setDeleteReason] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [savingInputs, setSavingInputs] = useState(false);
  const [syncOpen, setSyncOpen] = useState(false);

  const refreshHouseholds = useCallback(async () => {
    if (DEMO_MODE) {
      setHouseholds([DEMO_HOUSEHOLD]);
      setSelected(DEMO_HOUSEHOLD.id);
      return;
    }
    const data = await planningApi.households();
    setHouseholds(data.households);
    setSelected(current => data.households.some(household => household.id === current)
      ? current : data.households[0]?.id || '');
  }, []);

  useEffect(() => { refreshHouseholds().catch(e => setError(e.message)).finally(() => setLoading(false)); }, [refreshHouseholds]);
  useEffect(() => {
    if (DEMO_MODE) return;
    if (!selected) { setSummary(null); setProjection(null); return; }
    setLoading(true);
    Promise.all([planningApi.summary(selected), planningApi.facts(selected), planningApi.scenarios(selected)])
      .then(([s, f, sc]) => {
        setSummary(s); setFacts(f); setScenarios(sc.scenarios);
        setScenario(sc.scenarios.find(x => x.name === 'Proposed Plan')?.id || sc.scenarios[0]?.id || '');
        const people = (f.people as Array<Record<string, unknown>> | undefined) || [];
        const expenses = (f.expenses as Array<Record<string, unknown>> | undefined) || [];
        setRetirementAge(String(people[0]?.retirement_age || 65));
        setAnnualSpending(String(expenses[0]?.amount || 0));
      })
      .catch(e => setError(e.message)).finally(() => setLoading(false));
  }, [selected]);
  useEffect(() => {
    if (DEMO_MODE) return;
    if (!scenario) return;
    Promise.all([planningApi.project(scenario), planningApi.estate(scenario), planningApi.goals(scenario), planningApi.reportDefinitions(), planningApi.monteCarloInputs(scenario)])
      .then(([p, e, g, r, m]) => { setProjection(p); setEstate(e); setGoals(g.goals); setReports(r.definitions); setMcInputs(m); setMcResult(null); })
      .catch(e => setError(e.message));
  }, [scenario]);

  const chart = useMemo(() => projection?.rows.map(row => ({ ...row,
    inflows: Number(row.inflows), outflows: Number(row.outflows), taxes: Number(row.taxes),
    netWorth: Number(row.net_worth), age: row.client_age,
  })) || [], [projection]);

  async function createHousehold() {
    if (!newName.trim()) return;
    try {
      const result = await planningApi.create({ name: newName.trim(), people: [{ role: 'client', first_name: newName.split(' ')[0], last_name: newName.split(' ').slice(1).join(' '), date_of_birth: birthDate }], accounts: [], income: [], expenses: [], assumptions: {} });
      await refreshHouseholds(); setSelected(result.household_id); setCreateOpen(false); setNewName('');
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to create household'); }
  }

  async function importWarehouseHousehold() {
    if (!warehouseId.trim() || importing) return;
    try {
      setImporting(true);
      setImportError('');
      const result = await planningApi.importWarehouse(warehouseId.trim());
      await refreshHouseholds(); setSelected(result.household_id); setCreateOpen(false); setWarehouseId('');
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Unable to import warehouse household';
      setImportError(message);
      setError(message);
    } finally { setImporting(false); }
  }

  function openDeleteHousehold() {
    setDeleteConfirmation('');
    setDeleteReason('');
    setDeleteOpen(true);
  }

  async function deleteHousehold() {
    if (!selected || deleteConfirmation !== 'DELETE' || deleteReason.trim().length < 3) return;
    setDeleting(true);
    setError('');
    setNotice('');
    try {
      const started = await planningApi.deleteHousehold(selected, deleteReason.trim());
      for (let attempt = 0; attempt < 120; attempt += 1) {
        const job = await planningApi.job(started.job_id);
        if (job.status === 'succeeded') {
          setDeleteOpen(false);
          setDeleteConfirmation('');
          setDeleteReason('');
          setSelected('');
          setScenario('');
          setSummary(null);
          setFacts(null);
          setProjection(null);
          setMcInputs(null);
          setMcResult(null);
          await refreshHouseholds();
          setNotice('Household planning data was permanently deleted. Salesforce and Synapse source records were not changed.');
          return;
        }
        if (job.status === 'failed') throw new Error(job.error || 'Household deletion failed');
        await new Promise(resolve => window.setTimeout(resolve, 250));
      }
      throw new Error('Household deletion timed out');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to delete household');
    } finally {
      setDeleting(false);
    }
  }

  async function applyDecisionLevers() {
    if (!scenario) return;
    const overrides: unknown[] = [{ op: 'replace', path: '/people/0/retirement_age', value: Number(retirementAge) }];
    const expenses = (facts?.expenses as unknown[] | undefined) || [];
    if (expenses.length) overrides.push({ op: 'replace', path: '/expenses/0/amount', value: annualSpending });
    try {
      setApplying(true);
      await planningApi.overrides(scenario, overrides);
      const [nextProjection, nextEstate, nextGoals] = await Promise.all([
        planningApi.project(scenario), planningApi.estate(scenario), planningApi.goals(scenario),
      ]);
      setProjection(nextProjection); setEstate(nextEstate); setGoals(nextGoals.goals);
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to apply scenario'); }
    finally { setApplying(false); }
  }

  async function savePlanningInputs(draft: PlanningFactsDraft) {
    if (!selected) return false;
    const roots: Array<keyof PlanningFactsDraft> = [
      'name', 'people', 'accounts', 'liabilities', 'income', 'expenses',
      'goals', 'insurance', 'real_estate', 'transfers', 'assumptions',
    ];
    const writableRoots = String(summary?.source || '').toLowerCase() === 'datawarehouse'
      ? roots.filter(key => key !== 'accounts')
      : roots;
    try {
      setSavingInputs(true);
      setError('');
      setNotice('');
      await planningApi.patchFacts(selected, writableRoots.map(key => ({ op: 'replace', path: `/${key}`, value: draft[key] })));
      await planningApi.commitFacts(selected);
      const [nextSummary, nextFacts, nextScenarios] = await Promise.all([
        planningApi.summary(selected), planningApi.facts(selected), planningApi.scenarios(selected),
      ]);
      setSummary(nextSummary);
      setFacts(nextFacts);
      setScenarios(nextScenarios.scenarios);
      setScenario(nextScenarios.scenarios.find(item => item.name === 'Current Plan')?.id || nextScenarios.scenarios[0]?.id || '');
      await refreshHouseholds();
      setNotice('Planning inputs were validated and committed as a new facts version.');
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to save planning inputs');
      return false;
    } finally {
      setSavingInputs(false);
    }
  }

  async function runMonteCarlo() {
    if (!scenario || !mcInputs?.ready) return;
    setMcRunning(true);
    try {
      const started = await planningApi.runMonteCarlo(scenario);
      for (let attempt = 0; attempt < 120; attempt += 1) {
        const job = await planningApi.job(started.job_id);
        if (job.status === 'succeeded' && job.result) { setMcResult(job.result); setMcInputs(job.result.input_snapshot); return; }
        if (job.status === 'failed') throw new Error(job.error || 'Monte Carlo run failed');
        await new Promise(resolve => window.setTimeout(resolve, 500));
      }
      throw new Error('Monte Carlo run timed out');
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to run Monte Carlo'); }
    finally { setMcRunning(false); }
  }

  return <ThemeProvider theme={muiTheme}>
    <div className="has-sidenav">
    <SideNav />
    <Box className="plan-shell">
      {/* ── Allworth hero header ─────────────────────────────────────── */}
      <div className="plan-hero">
        <div className="plan-hero__topline">
          <ShareTool toolId="financial_planning" toolName="Financial Planning" />
          <div className="plan-hero__actions">
            <Chip icon={<CloudSyncOutlinedIcon sx={{ color: '#fff' }} />} label="Warehouse-backed" className="plan-source-chip" />
            <AuthControl />
          </div>
        </div>
        <div>
          <p className="plan-hero__eyebrow">Allworth Financial</p>
          <h1 className="plan-hero__title">Financial Planning</h1>
          <p className="plan-hero__subtitle">Retirement, tax, estate, and Monte Carlo planning on warehouse-backed facts</p>
        </div>
      </div>

      {/* ── Main content ─────────────────────────────────────────────── */}
      <Container maxWidth="xl" sx={{ py: 3, px: { xs: 1, sm: 2, md: 3 } }}>
        {error && <Alert severity="error" onClose={() => setError('')} sx={{ mb: 2 }}>{error}</Alert>}
        {notice && <Alert severity="success" onClose={() => setNotice('')} sx={{ mb: 2 }}>{notice}</Alert>}
        {loading && <Box className="plan-loading"><CircularProgress /></Box>}
        {!loading && !selected && <EmptyState onCreate={() => setCreateOpen(true)} />}
        {!loading && selected && <>
          <div className="plan-toolbar">
            <Box><Typography variant="h4">{String(summary?.name || '')}</Typography><Typography color="text.secondary">Living plan · warehouse-backed facts with advisor assumptions</Typography></Box>
            <Stack direction="row" sx={{ gap: 2, alignItems: 'center', flexWrap: 'wrap' }}>
              <FormControl size="small" sx={{ minWidth: 210 }}><InputLabel>Household</InputLabel><Select value={selected} label="Household" onChange={e => setSelected(e.target.value)}>
                {households.map(h => <MenuItem key={h.id} value={h.id}>{h.name}</MenuItem>)}</Select></FormControl>
              <FormControl size="small" sx={{ minWidth: 210 }}><InputLabel>Scenario</InputLabel><Select value={scenario} label="Scenario" onChange={e => setScenario(e.target.value)}>
                {scenarios.map(x => <MenuItem key={x.id} value={x.id}>{x.name}</MenuItem>)}</Select></FormControl>
              <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>New plan</Button>
            </Stack>
          </div>
          <Box sx={{ backgroundColor: colors.surfaceCard, borderRadius: 1, border: `1px solid ${colors.hairline}`, boxShadow: 'none', overflow: 'hidden' }}>
          <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" scrollButtons="auto" sx={{ borderBottom: `1px solid ${colors.hairline}`, px: 2, backgroundColor: colors.surfaceCard }}><Tab label="Overview" /><Tab label="Workspace" /><Tab label="Planning Inputs" /><Tab label="Cash Flow" /><Tab label="Decision Center" /><Tab label="Monte Carlo" /><Tab label="Lifecycle" /><Tab label="Goals" /><Tab label="Estate" /><Tab label="Tools" /><Tab label="Vault" /><Tab label="Client View" /><Tab label="Assumptions" /><Tab label="Reports" /></Tabs>
          <Box sx={{ px: 3, pb: 3 }}>
          {tab === 0 && <Box className="plan-panel"><Box className="plan-metrics">
            <Metric label="Current net worth" value={money(summary?.net_worth)} />
            <Metric label="Projected ending assets" value={money(projection?.ending_net_worth)} />
            <Metric label="Lifetime taxes" value={money(projection?.lifetime_taxes)} />
            <Metric label="First shortfall" value={projection?.first_shortfall_year ? String(projection.first_shortfall_year) : 'None'} tone={projection?.first_shortfall_year ? 'loss' : 'gain'} />
            <Metric label="Monte Carlo success" value={mcResult ? `${(mcResult.probability_of_success * 100).toFixed(0)}%` : mcInputs?.ready ? 'Ready' : 'Inputs needed'} tone={mcInputs?.ready ? 'gain' : 'loss'} />
          </Box>
          {String(summary?.source || '') === 'datawarehouse' &&
            <Button variant="outlined" startIcon={<CloudSyncOutlinedIcon />} sx={{ mb: 2 }} onClick={() => setSyncOpen(true)}>Plan vs actual</Button>}
          <Card><CardContent><Typography variant="h6">Projected net worth</Typography><Typography color="text.secondary" sx={{ mb: 2 }}>Deterministic annual ledger</Typography>
            <ResponsiveContainer width="100%" height={360}><AreaChart data={chart}><defs><linearGradient id="wealth" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#0C2E4E" stopOpacity={0.42}/><stop offset="95%" stopColor="#0C2E4E" stopOpacity={0.02}/></linearGradient></defs><CartesianGrid strokeDasharray="3 3" vertical={false}/><XAxis dataKey="year"/><YAxis tickFormatter={v => money(v, true)}/><Tooltip formatter={v => money(v)}/><Area type="monotone" dataKey="netWorth" stroke="#0C2E4E" fill="url(#wealth)" strokeWidth={3}/></AreaChart></ResponsiveContainer>
          </CardContent></Card></Box>}
          {tab === 1 && <WorkspaceTab householdId={selected} householdName={String(summary?.name || '')} onError={setError} />}
          {tab === 2 && <Box className="plan-panel plan-data"><PlanningInputs facts={facts} source={String(summary?.source || 'planning')} mcInputs={mcInputs} mcResult={mcResult} mcRunning={mcRunning} saving={savingInputs} onSave={savePlanningInputs} onRunMonteCarlo={runMonteCarlo} onDelete={openDeleteHousehold} /></Box>}
          {tab === 3 && <Box className="plan-panel"><Card><CardContent><Typography variant="h6">Cash flow and taxes</Typography><ResponsiveContainer width="100%" height={430}><BarChart data={chart}><CartesianGrid strokeDasharray="3 3" vertical={false}/><XAxis dataKey="year"/><YAxis tickFormatter={v => money(v, true)}/><Tooltip formatter={v => money(v)}/><Legend/><Bar dataKey="inflows" fill="#436434" stackId="in"/><Bar dataKey="outflows" fill="#A99C6C" stackId="out"/><Bar dataKey="taxes" fill="#D26D37" stackId="out"/></BarChart></ResponsiveContainer></CardContent></Card></Box>}
          {tab === 4 && <DecisionTab scenario={scenario} scenarios={scenarios} householdId={selected} chart={chart}
            retirementAge={retirementAge} annualSpending={annualSpending} applying={applying}
            onRetirementAge={setRetirementAge} onAnnualSpending={setAnnualSpending} onApply={() => void applyDecisionLevers()} onError={setError} />}
          {tab === 5 && <MonteCarloTab mcInputs={mcInputs} mcResult={mcResult} mcRunning={mcRunning} onRun={() => void runMonteCarlo()} />}
          {tab === 6 && <LifecycleTab scenario={scenario} onError={setError} />}
          {tab === 7 && <Box className="plan-panel"><Card><CardContent><Typography variant="h6">Goal Planner</Typography><Typography color="text.secondary" sx={{ mb: 2 }}>Goals are evaluated against the same tax-aware annual ledger, not a separate calculator.</Typography>{goals.length ? <Box className="plan-report-grid">{goals.map(goal => <Card key={goal.id} variant="outlined"><CardContent><Typography variant="subtitle1">{goal.name}</Typography><Chip size="small" color={goal.status === 'funded' ? 'success' : 'warning'} label={`${Number(goal.funded_pct).toFixed(0)}% funded`} /><Typography sx={{ mt: 1 }}>{money(goal.available)} available in {goal.target_year}</Typography><Typography color="text.secondary">Target {money(goal.target_amount)} · shortfall {money(goal.shortfall)}</Typography></CardContent></Card>)}</Box> : <Alert severity="info">No goals are present in the current warehouse facts. Add retirement, education, legacy, or major-purchase goals in Planning Inputs.</Alert>}</CardContent></Card></Box>}
          {tab === 8 && <EstateTab scenario={scenario} estate={estate} onError={setError} />}
          {tab === 9 && <ToolsTab onError={setError} />}
          {tab === 10 && <VaultTab householdId={selected} onError={setError} />}
          {tab === 11 && <ClientViewTab householdId={selected} summary={summary} goals={goals} onError={setError} />}
          {tab === 12 && <AssumptionsTab onError={setError} />}
          {tab === 13 && <ReportsTab householdId={selected} scenario={scenario} reports={reports} onError={setError} />}
          </Box>
          </Box>
        </>}
      </Container>
      <Dialog open={createOpen} onClose={() => { if (!importing) setCreateOpen(false); }} fullWidth maxWidth="sm"><DialogTitle>Start a planning household</DialogTitle><DialogContent><Stack sx={{ gap: 2, mt: 1 }}><Typography variant="subtitle2">Import from DataWarehouse</Typography>{importError && <Alert severity="error" onClose={() => setImportError('')}>{importError}</Alert>}{importing && <Alert severity="info" icon={<CircularProgress size={20} />}>Importing household data from Synapse. Contacts, accounts, holdings, and planning inputs can take 20–30 seconds.</Alert>}<TextField autoFocus label="Salesforce ID or exact household name" value={warehouseId} onChange={e => setWarehouseId(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') void importWarehouseHousehold(); }} disabled={importing} helperText="Example: Mahler, Kevin and Melanie. Exact warehouse names and 15/18-character Salesforce IDs are supported."/><Button variant="contained" onClick={importWarehouseHousehold} disabled={!warehouseId.trim() || importing}>{importing ? 'Importing from Synapse…' : 'Import household'}</Button><Divider>or create a draft</Divider><TextField label="Household name" value={newName} onChange={e => setNewName(e.target.value)} disabled={importing} /><TextField label="Primary client date of birth" type="date" value={birthDate} onChange={e => setBirthDate(e.target.value)} disabled={importing} slotProps={{ inputLabel: { shrink: true } }} /></Stack></DialogContent><DialogActions><Button onClick={() => setCreateOpen(false)} disabled={importing}>Cancel</Button><Button variant="outlined" onClick={createHousehold} disabled={!newName.trim() || importing}>Create draft</Button></DialogActions></Dialog>
      <Dialog open={deleteOpen} onClose={() => { if (!deleting) setDeleteOpen(false); }} fullWidth maxWidth="sm"><DialogTitle>Delete household?</DialogTitle><DialogContent><Stack sx={{ gap: 2, mt: 1 }}><Alert severity="warning">This permanently deletes the planning copy of <strong>{String(summary?.name || '')}</strong>, including scenarios, facts versions, portal records, vault files, and cached projections. Source records in Salesforce and Synapse are not changed.</Alert><TextField label="Reason for deletion" value={deleteReason} onChange={e => setDeleteReason(e.target.value)} required helperText="Recorded in the audit log (minimum 3 characters)." slotProps={{ htmlInput: { maxLength: 500 } }} /><TextField label='Type "DELETE" to confirm' value={deleteConfirmation} onChange={e => setDeleteConfirmation(e.target.value)} required autoComplete="off" /></Stack></DialogContent><DialogActions><Button onClick={() => setDeleteOpen(false)} disabled={deleting}>Cancel</Button><Button color="error" variant="contained" onClick={deleteHousehold} disabled={deleting || deleteConfirmation !== 'DELETE' || deleteReason.trim().length < 3}>{deleting ? 'Deleting…' : 'Permanently delete'}</Button></DialogActions></Dialog>
      <SyncActualsDialog open={syncOpen} householdId={selected} onClose={() => setSyncOpen(false)}
        onApplied={() => {
          Promise.all([planningApi.summary(selected), planningApi.facts(selected)])
            .then(([s, f]) => { setSummary(s); setFacts(f); })
            .catch(e => setError(e instanceof Error ? e.message : 'Unable to refresh household'));
          if (scenario) planningApi.project(scenario).then(setProjection).catch(() => undefined);
        }}
        onError={setError} />
    </Box>
    </div>
  </ThemeProvider>;
}
