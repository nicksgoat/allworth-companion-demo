import { useCallback, useEffect, useState } from 'react';
import {
  Alert, Box, Card, CardContent, Chip, CircularProgress, LinearProgress, List,
  ListItem, ListItemText, Typography,
} from '@mui/material';
import { planningApi, type PortalRecord, type VaultFile } from '../services/planningApi';
import { Kpi, money } from './shared';

interface Props {
  householdId: string;
  summary: Record<string, unknown> | null;
  goals: Array<Record<string, string>>;
  onError: (message: string) => void;
}

/** Advisor-side preview of exactly what the client portal exposes. */
export default function ClientViewTab({ householdId, summary, goals, onError }: Props) {
  const [sharedFiles, setSharedFiles] = useState<VaultFile[]>([]);
  const [budgets, setBudgets] = useState<PortalRecord[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [vault, budgetData] = await Promise.all([
        planningApi.vaultFiles(householdId),
        planningApi.portalRecords(householdId, 'budgets'),
      ]);
      setSharedFiles(vault.files.filter(file => file.shared_with_client));
      setBudgets(budgetData.budgets || []);
    } catch (e) { onError(e instanceof Error ? e.message : 'Unable to load client view'); }
    finally { setLoading(false); }
  }, [householdId, onError]);

  useEffect(() => { void load(); }, [load]);

  if (loading) return <Box className="plan-loading"><CircularProgress /></Box>;

  return <Box className="plan-panel">
    <Alert severity="info" sx={{ mb: 2 }}>
      Preview of the client experience: only committed plan facts, funded goals, budgets, and vault
      documents explicitly shared with the client are visible here. Scenario mechanics, overrides,
      and advisor tooling are hidden from clients by the API's household isolation.
    </Alert>
    <Box className="plan-metrics" sx={{ gridTemplateColumns: 'repeat(3, minmax(0,1fr))' }}>
      <Kpi label="Total assets" value={money(summary?.total_assets)} />
      <Kpi label="Total liabilities" value={money(summary?.total_liabilities)} />
      <Kpi label="Net worth" value={money(summary?.net_worth)} tone="gain" />
    </Box>
    <Card><CardContent>
      <Typography variant="h6">Goal progress</Typography>
      <Typography color="text.secondary" sx={{ mb: 2 }}>Funding status the client sees for each committed goal.</Typography>
      {goals.length === 0 ? <Alert severity="info">No goals are committed to the plan yet.</Alert>
        : goals.map(goal =>
          <Box key={goal.id} sx={{ mb: 2 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
              <Typography>{goal.name}</Typography>
              <Chip size="small" color={goal.status === 'funded' ? 'success' : 'warning'}
                label={`${Number(goal.funded_pct).toFixed(0)}% funded`} />
            </Box>
            <LinearProgress variant="determinate" value={Math.min(100, Number(goal.funded_pct))} sx={{ height: 8, borderRadius: 4 }} />
            <Typography variant="caption" color="text.secondary">
              {money(goal.available)} of {money(goal.target_amount)} by {goal.target_year}
            </Typography>
          </Box>)}
    </CardContent></Card>
    <Box className="plan-decision" sx={{ gridTemplateColumns: { md: 'repeat(2, minmax(0,1fr))' }, mt: 2.5 }}>
      <Card><CardContent>
        <Typography variant="h6">Shared documents</Typography>
        <Typography color="text.secondary" sx={{ mb: 1 }}>Vault files marked "shared with client".</Typography>
        {sharedFiles.length === 0 ? <Alert severity="info">No documents are shared with the client.</Alert>
          : <List dense>{sharedFiles.map(file =>
            <ListItem key={file.id} disableGutters>
              <ListItemText primary={file.name}
                secondary={`${file.folder} · ${new Date(file.uploaded_at).toLocaleDateString()}`} />
            </ListItem>)}</List>}
      </CardContent></Card>
      <Card><CardContent>
        <Typography variant="h6">Budgets</Typography>
        <Typography color="text.secondary" sx={{ mb: 1 }}>Spending plans visible in the client portal.</Typography>
        {budgets.length === 0 ? <Alert severity="info">No budgets have been created.</Alert>
          : <List dense>{budgets.map(record =>
            <ListItem key={record.id} disableGutters>
              <ListItemText primary={String(record.payload.title || record.payload.category || 'Budget')}
                secondary={record.payload.amount ? money(record.payload.amount) : undefined} />
            </ListItem>)}</List>}
      </CardContent></Card>
    </Box>
  </Box>;
}
